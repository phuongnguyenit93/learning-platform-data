# schedule() to Run Once at a Specified Time

## 1. Goal: Scheduling a One-Time Task with TaskScheduler

In Spring Framework, `TaskScheduler` is the abstraction used to request that a `Runnable` run **at a specified time** or according to recurring rules. When an application needs to send a reminder, perform a post-processing step, trigger a status check, or run a task after a user-selected time, the most direct API is:

```java
ScheduledFuture<?> handle = taskScheduler.schedule(
        runnable,
        startTime   // java.time.Instant
);
```

With the **`schedule(Runnable, Instant)`** overload, the task is **scheduled to run once**. There is no `period`, no cron repetition, and it does not automatically create a series of runs. This is a key difference compared to `scheduleAtFixedRate(...)`, `scheduleWithFixedDelay(...)`, or `schedule(Runnable, Trigger)`.

**Two things must be distinguished:**

1. **Accepting the schedule:** when calling `schedule(...)` succeeds, the scheduler holds a task that will become due at the requested time.
2. **Actually running and completing:** the scheduler must still be alive, have an available worker, and required dependencies must still be working when it becomes due.

An accepted schedule does not mean the work has run, does not guarantee millisecond-exact execution, and **does not automatically guarantee survival across JVM/process restarts**.

### Learning Objectives

After this lesson, you will be able to:

- Call `TaskScheduler.schedule(Runnable, Instant)` properly to create a **one-shot task**.
- Use `Instant`, `ZoneId`, and `LocalDateTime` properly when users enter local time.
- Understand future times, past times, and what happens when the scheduler is overloaded.
- Use `ScheduledFuture<?>` to check status, wait for completion, observe errors, or request cancellation.
- Configure a `ThreadPoolTaskScheduler` bean and call it from a Spring service.
- Write runnable Java 17 examples with deterministic results instead of using `Thread.sleep(...)` to guess whether a task ran.
- Avoid pitfalls related to scheduler threads, application shutdown, multiple instances, and schedules requiring durable storage.

## 2. API Contract: TaskScheduler.schedule(Runnable, Instant)

Spring's interface provides the method:

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
```

Where:

- **`task`:** the work implementing `Runnable`, typically a lambda `() -> doSomething()`. Because `Runnable.run()` returns `void`, the future of a normally completed task contains no business value.
- **`startTime`:** the desired execution time represented as `java.time.Instant`, i.e., an absolute point in time on the UTC timeline.
- **Return value:** `ScheduledFuture<?>` to manage the scheduled run, e.g., `isDone()`, `cancel(...)`, `getDelay(...)`, `get(...)`.
- **If `startTime` is already in the past:** per the API contract, the work will be executed **as soon as possible**, without automatically throwing an error solely because the time has passed.
- **If the scheduler does not accept the task:** it may throw `TaskRejectedException`, for example when the scheduler is shutting down or due to internal limits/rejection policies.
- **If the time becomes due while workers are busy:** the run may start **later** than the requested time; this is best-effort scheduling on an executor, not a hard real-time mechanism.

Example scheduling 3 seconds from now:

```java
Instant fireAt = Instant.now().plusSeconds(3);
ScheduledFuture<?> handle = taskScheduler.schedule(
        () -> System.out.println("Run once"),
        fireAt
);
```

This is an **integration snippet**, assuming `taskScheduler` is an injected/initialized bean, not a standalone Java class. The `schedule` call returns immediately after submitting the schedule under normal conditions; the caller thread **does not wait three seconds**. When a scheduler worker is available to serve it, the callback will be invoked at or after `fireAt`.

### Do Not Confuse “On Time” with “Exact to the Nanosecond”

`Instant` can hold nanosecond precision at the data-type level, yet execution also depends on clock/timer resolution, the CPU scheduler, GC, locks, the thread pool, the duration of other tasks, contention, and machine load. Therefore, the right condition for many applications is “not before the desired time, running as close to that time as possible,” rather than guaranteeing the actual timestamp matches the input `Instant` identically.

If business logic requires a strict cutoff, define a **deadline**, measure lateness, and decide what constitutes running too late; do not use `schedule` as a hard real-time clock.

## 3. Timeline of a One-Time Task

Consider a request at 10:00:00 scheduling a run at 10:00:05:

```text
caller thread                 scheduler                       worker thread
     |                           |                                  |
     |  schedule(task, t=10:00:05)                                  |
     |-------------------------->|                                  |
     |                           | holds delayed task               |
     |<------ ScheduledFuture ---|                                  |
     |                           |                                  |
     |        caller can continue handling requests                 |
     |                           |                                  |
     |                    due at 10:00:05                           |
     |                           |-- dispatch when worker free ---->|
     |                           |                                  | task.run()
     |                           |                                  | completes
     |                           |<------------------- future done -|
     |                           |                                  |
     |                         DOES NOT repeat                      |
```

Key states:

| Phase | Meaning | What Can Observe It? |
| --- | --- | --- |
| Just submitted | Scheduler accepted the schedule | `ScheduledFuture<?>` returned; no rejection |
| Waiting until due | Task has not run yet | `future.isDone()` is usually `false`; `getDelay(...)` is positive (approx.) |
| Due, waiting for worker | Time has passed but execution hasn't started due to busy/congestion | Queue metrics, active workers, lateness |
| Running | `Runnable.run()` is executing | Instrument task start/end; future is usually not done yet |
| Completed normally | `run()` returned | `future.isDone() == true`; `get()` finishes |
| Completed with exception | Task threw an error and the executor recorded the exception per implementation | `get()` may throw `ExecutionException` |
| Cancelled | Cancellation request was accepted | `isCancelled()`; `get()` throws `CancellationException` |

**Note:** `ScheduledFuture.getDelay(TimeUnit)` represents the estimated remaining time until the scheduled fire time, **not** whether the task has finished running. Once overdue, the delay may be zero or negative while the task has still not completed.

To know whether the task **has completed**, use `future.get(timeout, unit)` in environments that allow blocking, or application-level instrumentation/callbacks/status tables; do not only read the delay.

## 4. Complete Java 17 + Spring Framework 6.2 Example: One Run and One Cancellation

The example uses `ThreadPoolTaskScheduler` directly, a common Spring implementation. We initialize the scheduler in code so the program **can run outside Spring Boot** without deploying a server. With a Spring-managed bean in a real application, the lifecycle is managed by the ApplicationContext; this CLI example calls `initialize()` and `shutdown()` itself.

**Prerequisites:** JDK 17+, Maven 3.x, Spring Framework `6.2.14`.

Directory structure:

```text
spring-one-shot/
├── pom.xml
└── src/main/java/demo/OneShotDemo.java
```

### 4.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-one-shot</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.OneShotDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.2. src/main/java/demo/OneShotDemo.java

```java
package demo;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public final class OneShotDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("one-shot-");
        scheduler.initialize(); // Because the example runs outside a Spring ApplicationContext.

        AtomicInteger runs = new AtomicInteger();
        AtomicBoolean properThread = new AtomicBoolean(false);
        AtomicInteger cancelledRuns = new AtomicInteger();

        try {
            Instant runAt = Instant.now().plusMillis(250);

            ScheduledFuture<?> first = scheduler.schedule(() -> {
                properThread.set(
                        Thread.currentThread().getName()
                                .startsWith("one-shot-"));
                runs.incrementAndGet();
            }, runAt);

            // CLI demo may block to verify that the task has finished.
            first.get(5, TimeUnit.SECONDS);
            System.out.println("onSchedulerThread=" + properThread.get());
            System.out.println("completedRuns=" + runs.get());
            System.out.println("firstDone=" + first.isDone());

            // Another run scheduled far in the future and cancelled immediately.
            ScheduledFuture<?> later = scheduler.schedule(
                    () -> cancelledRuns.incrementAndGet(),
                    Instant.now().plus(Duration.ofDays(1)));

            boolean accepted = later.cancel(false);
            System.out.println("cancelAccepted=" + accepted);
            System.out.println("laterCancelled=" + later.isCancelled());
            System.out.println("laterRuns=" + cancelledRuns.get());
        } finally {
            scheduler.shutdown();
        }
    }
}
```

Run inside the `spring-one-shot` directory:

```bash
mvn -q compile exec:java
```

**Expected standard output when the program runs normally:**

```text
onSchedulerThread=true
completedRuns=1
firstDone=true
cancelAccepted=true
laterCancelled=true
laterRuns=0
```

### 4.3. Analyzing the Program's Behavior

1. `scheduler.initialize()` creates the underlying scheduled executor. If you omit this step when instantiating the object outside a Spring context, the scheduler is not yet ready to accept schedules.
2. `setThreadNamePrefix("one-shot-")` allows checking that the task ran on a thread created by the scheduler; the program prints a boolean rather than printing a thread name with a non-fixed sequence number.
3. `Instant.now().plusMillis(250)` sets a short future time. Actual timing can vary by a few milliseconds, but `first.get(5, ...)` **waits until the task completes**, so the run-count check does not rely on `Thread.sleep`.
4. `runs.incrementAndGet()` is called only once by the one-shot task; the normal result is `completedRuns=1`. `first.isDone()` becomes true after the task finishes.
5. The second task is scheduled one day ahead and cancelled **before its due time**. `later.cancel(false)` is accepted, `later.isCancelled()` is true, and `cancelledRuns` remains 0.
6. `finally` shuts down the scheduler. This part is crucial for CLIs/tests: if you create a thread pool and don't shut it down, the process may keep live threads running. In a real Spring context, use the bean lifecycle instead of creating a new scheduler per request.

**Do not overgeneralize:** this is a simple scenario—one JVM, no restarts, low latency, and no DB/APIs. It demonstrates one-shot scheduling and cancellation before execution, **not absolute precision or survival across server shutdowns**. Do not assert hardcoded timestamp output lines because wall-clock time always differs.

If an extremely overloaded environment prevents the task from completing within 5 seconds, `get(5, ...)` will throw `TimeoutException`: that is a test failure condition rather than producing the expected six output lines.

## 5. Using TaskScheduler as a Spring Bean in Real Applications

In a Spring Framework / Spring Boot application, you should manage the scheduler via the container and inject it through the `TaskScheduler` abstraction, rather than calling `new ThreadPoolTaskScheduler()` on every incoming request.

**SchedulingConfiguration.java** — example integration configuration class:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class SchedulingConfiguration {

    @Bean("oneShotScheduler")
    public ThreadPoolTaskScheduler oneShotScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("reminder-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

This is an **integration class**, not a standalone file runnable with `javac` alone: the application must have a Spring context and place the configuration under appropriate component scanning/importing. Spring will invoke the lifecycle initialization/destruction of the `ThreadPoolTaskScheduler` bean; there is no need to call `initialize()` manually on a normally managed bean.

**ReminderService.java** — accepts a request to schedule exactly once:

```java
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.ScheduledFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class ReminderService {
    private final TaskScheduler scheduler;
    private final ReminderSender sender;

    public ReminderService(
            @Qualifier("oneShotScheduler") TaskScheduler scheduler,
            ReminderSender sender) {
        this.scheduler = scheduler;
        this.sender = sender;
    }

    public ScheduledFuture<?> scheduleReminder(String reminderId, Instant at) {
        Objects.requireNonNull(reminderId, "reminderId");
        Objects.requireNonNull(at, "at");

        return scheduler.schedule(
                () -> sender.sendReminder(reminderId),
                at);
    }
}
```

Here `ReminderSender` is an **application-defined business service**, and a corresponding bean must be provided. The snippet illustrates the API, not a complete program until `ReminderSender`, main/bootstrapping, configuration, and dependencies are present.

**Caller example:**

```java
Instant at = Instant.parse("2026-11-01T02:00:00Z");
ScheduledFuture<?> handle =
        reminderService.scheduleReminder("REM-100", at);
```

The caller receives the handle after the scheduler accepts the schedule; it **does not** receive “reminder sent successfully”. In a web endpoint, you should not call `handle.get()` immediately if doing so would make the request thread wait until a scheduled time hours later.

### Is @EnableScheduling Required?

**It is not required solely to call `TaskScheduler.schedule(...)` programmatically on an already-initialized bean.** `@EnableScheduling` primarily activates the infrastructure that processes `@Scheduled` methods in the Spring context. Both approaches can coexist, but they differ in how registration works:

- `TaskScheduler.schedule(Runnable, Instant)`: the caller decides a specific point in time and actively creates a schedule.
- `@Scheduled`: the method is registered by the framework from schedule metadata on the bean, usually for cron/fixed-rate/fixed-delay or one-time delay mechanisms supported by a given version.

For a feature like “the user schedules a notification at 09:00 on day X” that varies per request, calling `schedule(...)` directly is usually clearer than trying to attach annotations for thousands of dynamic timestamps.

## 6. Instant, Time Zones, and User-Entered Times

`Instant` represents **an absolute point in time**, carrying no local time zone name. User interfaces, however, commonly accept inputs like:

```text
"01/11/2026 09:00"    (local time)
```

This string alone is not enough to identify a global point in time: you must know the **user's or business domain's time zone**. Do not take the Docker server's default timezone and treat it as every customer's timezone.

Example converting 09:00 in Vietnam on November 1, 2026 to `Instant`:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 9, 0);
Instant fireAt = local.atZone(zone).toInstant();

System.out.println(fireAt);
// 2026-11-01T02:00:00Z
```

This is a **snippet** inside a method with appropriate imports. The `Asia/Ho_Chi_Minh` time zone currently uses UTC+07:00, so the conversion yields 02:00 UTC. Choose `ZoneId` based on business data; a single server can serve multiple zones.

### Daylight Saving Time (DST)

Some time zones observe daylight saving time and DST transitions:

- A `LocalDateTime` may **not exist** locally when the clock jumps forward to a new hour.
- A `LocalDateTime` may occur **twice** when the clock falls back.
- `local.atZone(zone)` applies default adjustment/offset-selection rules; do not assume those always match your desired business decision.
- If high schedule accuracy is needed, validate with `zone.getRules().getValidOffsets(local)`. A list with 0 offsets means a gap, and 2 offsets means an overlap; ask the user to resolve it or pick a clearly defined policy.

If users pick an absolute time via an API, you can accept ISO-8601 with an offset, convert it to `Instant`, and also store the original zone if you later need to display it correctly in local time. Do not construct future schedules by adding a fixed number of hours instead of using time zone rules when computing “tomorrow at 9 AM” in a DST zone.

### Will a Past Time Still Run?

By the `schedule(Runnable, Instant)` contract, a past time will run **as soon as possible**. For instance, a request passing `Instant.now().minusSeconds(10)` is not automatically “invalid”.

However, business logic may want to **reject overdue schedules**:

```java
if (!requestedTime.isAfter(scheduler.getClock().instant())) {
    throw new IllegalArgumentException("Schedule time must be future");
}
ScheduledFuture<?> future = scheduler.schedule(job, requestedTime);
```

This snippet assumes `requestedTime`, `job`, and `scheduler` are already initialized. This is a business check, **not an automatic API rule**; between the check and submission there is still a race if time ticks past. If you need to handle that case, specify “run immediately”, “reject”, or “mark missed” explicitly instead of silently assuming.

## 7. ScheduledFuture: Tracking, Waiting, and Cancelling

`schedule(...)` returns a `ScheduledFuture<?>` combining the `Future` API with the `Delayed` delay-query API.

| Method | What Is It Used For? | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| `getDelay(unit)` | Estimates how much time remains until due | Does not confirm whether the task started/completed |
| `isDone()` | Future is finished per its state | Not necessarily success (could be error/cancelled) |
| `isCancelled()` | Future is in cancelled state | Does not prove any side effects were rolled back |
| `cancel(false)` | Attempts to cancel the schedule; does not request interrupting a running task | Does not guarantee stopping a task that already started |
| `cancel(true)` | Attempts to cancel, may request interrupting a running task per implementation | Does not guarantee JDBC/HTTP/remote operations stop immediately |
| `get()` | Waits until the task completes, fails, or is cancelled | Can block the caller for a very long time |
| `get(timeout, unit)` | Waits for a bounded time for the result | Timing out the wait does **not** cancel the task |

**Capturing state in tests/CLIs:**

```java
try {
    future.get(5, TimeUnit.SECONDS);
    System.out.println("success=true");
} catch (java.util.concurrent.CancellationException ex) {
    System.out.println("cancelled=true");
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable original = ex.getCause();
    System.err.println("Task failed: " + original);
} catch (java.util.concurrent.TimeoutException ex) {
    System.err.println("Still waiting or running");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
```

The snippet assumes `future` exists and `TimeUnit` is imported. Use `get()` in a request handler only when there is a valid reason to block; most scheduling endpoints should **return an acknowledgement that the request was accepted along with a tracking ID**, not wait hours to send a response.

### Cancelling Before Due Time

If the task has not started yet, `future.cancel(false)` usually prevents the task from executing. With a `ThreadPoolTaskScheduler` backed by `ScheduledThreadPoolExecutor`, cancelling a delayed task also involves the **remove-on-cancel** policy: a cancelled task may remain retained in the queue until its trigger time unless removal on cancel is enabled.

Depending on configuration/version, this can be enabled on the underlying executor:

```java
scheduler.getScheduledThreadPoolExecutor()
         .setRemoveOnCancelPolicy(true);
```

This snippet can only be called when `ThreadPoolTaskScheduler` **has already been initialized** and the underlying implementation is `ScheduledThreadPoolExecutor`. It affects how cancelled tasks are retained in the queue, and does not change the meaning of `cancel(...)` for work that has already started running.

### Cancelling After the Task Has Started

`cancel(false)` does not send an interrupt; `cancel(true)` may cause the worker to be interrupted per executor semantics, but the task must **cooperate** to stop. When the Runnable is calling a remote service or running a DB transaction, do not treat a cancelled future as proof that the remote request never happened. For tasks with side effects, you need cancellation-aware clients, timeouts, transactions, and idempotency.

If `cancel(...)` returns `false`, the task may have already completed, been cancelled earlier, or cannot be cancelled in its current state. Do not treat `false` as “ran successfully” without checking the outcome.

## 8. Errors in Runnable and Errors at Schedule Registration

There are **two distinct places** where errors can surface:

### 8.1. Errors at Submission Time

If the scheduler is shutting down or rejects the schedule for an internal reason, `schedule(...)` may throw `TaskRejectedException` **directly on the caller**:

```java
try {
    ScheduledFuture<?> handle = scheduler.schedule(job, when);
    // Schedule accepted, does NOT mean the job has completed.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Schedule was NOT accepted by the scheduler: return an appropriate error,
    // or persist via a durable mechanism and retry with a bound.
}
```

This snippet requires `scheduler`, `job`, and `when` to be available in integration code. Rejection at submission time does not mean the task ran and threw an exception; the callback may never have started at all.

### 8.2. Errors When the Job Executes

If `Runnable.run()` has started running and throws a `RuntimeException`, the scheduler may record the error on the Future and/or pass it to an `ErrorHandler` depending on the implementation and configuration. For one-shot scheduling on `ThreadPoolTaskScheduler` under default error handling, an exception from the run can surface via `ScheduledFuture.get()` as an `ExecutionException`; if the application configures a custom `ErrorHandler` that swallows errors, observed semantics can change.

Important point: **do not assume exceptions will be thrown back onto the thread that called `schedule(...)`**. The caller thread has usually moved on long ago.

A Runnable with business error handling:

```java
Runnable job = () -> {
    try {
        sender.sendReminder("REM-100");
    } catch (RemoteServiceException ex) {
        metric.increment();
        throw ex;
    }
};
```

This is an illustrative snippet with application-defined `sender`, `RemoteServiceException`, and `metric`. If retries are needed, define an explicit retry budget, idempotency, and job status; do **not** assume Spring will automatically re-run a one-shot task after an exception.

### 8.3. Do Not Forget ErrorHandler

`ThreadPoolTaskScheduler.setErrorHandler(...)` lets you configure how errors from tasks are reported. The handler choice must fit one-shot vs. recurring tasks: if the handler only logs and suppresses, the callback may appear to have completed normally at the future/scheduler layer even though the business operation failed. Therefore there must be **a single place owning the job's FAILED state**, rather than relying solely on worker logs.

For important tasks, store a job ID/status before registering, and then mark `RUNNING`/`SUCCEEDED`/`FAILED` from the business boundary. Do not rely solely on `future.isDone()` to decide whether sending succeeded.

## 9. Differences Between One-Time schedule() and Recurring Schedules

| API | Characteristics | Suitable Scenarios |
| --- | --- | --- |
| `schedule(Runnable, Instant)` | **Once**, at/after Instant | Sending a reminder at a specified time |
| `schedule(Runnable, Trigger)` | Schedule determined by Trigger; may keep producing runs | Cron, custom schedules |
| `scheduleAtFixedRate(Runnable, Duration)` | Repeats at a fixed cadence | Periodic metric collection |
| `scheduleAtFixedRate(Runnable, Instant, Duration)` | Has a start time and fixed period | Starting a periodic job from mark X |
| `scheduleWithFixedDelay(Runnable, Duration)` | Waits an interval after the previous run finishes | Polling with a pause between runs |
| `scheduleWithFixedDelay(Runnable, Instant, Duration)` | Has an initial mark and delay after the previous run | Polling starting from a chosen mark |

**Common pitfall:** wanting to send an email once at 17:00 but using `scheduleAtFixedRate(task, Duration.ofHours(24))`. That continues sending emails on subsequent days. When you want exactly once, use `schedule(task, instant)`.

If you want a schedule **daily at 09:00 in a time zone**, that is a recurrence problem involving DST and time zones, not equivalent to “adding 24 hours to an Instant” in DST zones. Use an appropriate Trigger/Cron or a durable scheduler following business rules.

### Difference Between TaskScheduler and TaskExecutor

`TaskExecutor.execute(task)` typically requests execution as soon as possible; `TaskScheduler.schedule(task, instant)` requests **not running before the specified mark**, and then running when resources allow. Both are subject to thread, queue, scheduling, and shutdown constraints, but one carries a **future target time**.

## 10. Execution Capacity: Scheduler Threads, Pool Size, and Delays

`ThreadPoolTaskScheduler` wraps the JDK's `ScheduledThreadPoolExecutor`. In Spring Framework 6.2, the default `poolSize` is **1**. You should not infer from the name “thread pool scheduler” that it has multiple workers by default.

Notably, per the Javadoc, `ThreadPoolTaskScheduler` tasks **run on the scheduler threads themselves**, rather than automatically being handed off to a separate execution pool. Consequently:

- A long-running task can occupy the scheduler thread and force other due jobs to wait.
- With pool size 1, one-shot jobs may start sequentially even if they share the exact same `Instant`.
- Increasing pool size can allow multiple due tasks to run concurrently, but does not increase DB connections or remote quotas.
- A scheduler thread waiting on the network still occupies a scheduler worker if using blocking clients.
- The scheduled queue in memory is not a durable on-disk job queue.

Example of two jobs due at the same time on a scheduler with pool size 1:

```text
T = 10:00:00
Job A (runs 8 seconds) --------+-------------------->
                               |
Job B (due also at 10:00:00)   | [waiting for worker]
                               +----> starts after A finishes
```

Therefore, `Instant` is a **desired time**, not a guaranteed deadline. If an important job must trigger on time, measure **scheduling lag** = actualStart - desiredTime and define an overdue-handling policy.

### Should You Schedule a Runnable That Submits to Another Executor?

You can use a **very short** Runnable at the due time to submit heavy work to a separate executor:

```java
scheduler.schedule(
        () -> workerExecutor.execute(
                () -> reportService.generateReport(reportId)),
        runAt);
```

This is an integration snippet with existing `scheduler`, `workerExecutor`, `reportService`, `reportId`, and `runAt`. **Important warning:** the future returned by `schedule(...)` in this example tracks **submission to the worker executor**, not the entire `generateReport` running on another worker. If the worker executor rejects it, that must also be handled explicitly. If you need the business result, store a task ID and status, or build proper `CompletableFuture`/completion tracking.

Do not spawn a new thread per task just to avoid a small scheduler pool; choose a bounded executor and account for downstream capacity, memory, and backpressure.

### Monitoring Metrics

Useful metrics:

- Counts of scheduled, due, started, completed, failed, and cancelled jobs.
- Queue depth, active scheduler threads, pool size, and rejected schedules.
- Scheduling lag from desired `Instant` to actual start, p50/p95/p99 distributions.
- Execution duration, concurrent running jobs, and total overdue backlog.
- JDBC/HTTP pool saturation if callbacks call downstream dependencies.
- Number of schedules far in the future, and cancelled tasks still sitting in the queue.

With Spring Boot Actuator/Micrometer, exact metrics depend on how executors/schedulers are bound and the version. Do not assume `getPoolSize()` or `getActiveCount()` automatically appear on dashboards if the application has not configured instrumentation.

## 11. Shutdown, Restart, and Multiple Instances: The Biggest Limitation of In-Memory One-Shots

A call to `scheduler.schedule(job, when)` with `ThreadPoolTaskScheduler` keeps the schedule in the **memory of the current JVM**. This has consequences:

### 11.1. Application Restarts Before Execution Time

If the JVM stops and restarts, the `ScheduledFuture` handle from the old process cannot be reused. Schedules waiting in the scheduled executor are not automatically restored from a DB either. If the application needs schedules to survive restarts, it must **persist schedule data durably** and have a recovery mechanism.

Even if shutdown is configured to “wait for tasks to complete”, a restart/deploy still does not create a durable scheduling system for schedules days away. Do not hold an HTTP request or delay JVM shutdown until a scheduled date just to preserve an unpersisted schedule.

### 11.2. Multiple Instances Registering the Same Job

If the application runs 4 pods and each pod calls `schedule(job, when)` for the same job ID, there can be **4 duplicate executions** when due. Local `TaskScheduler` has no built-in distributed lock or exactly-once coordination.

If only one pod receives the request and holds the schedule, and that pod dies, the schedule can be lost; a load balancer routing subsequent requests to another pod also does not transfer the `ScheduledFuture` from the old JVM.

### 11.3. Need for Idempotency and Durable State

For critical work such as sending invoices, transitioning order states, or sending costly notifications, the architecture should include:

```text
API receives scheduling request
       |
       v
DB saves: job_id, execute_at (Instant), status, payload/ref, version
       |
       v
worker/scheduler finds due jobs
       |
       v
atomic claim / transaction / lease by job_id
       |
       v
run idempotent processing
       |
       +--> SUCCEEDED
       +--> FAILED / RETRY_AT
```

Consider downstream **idempotency keys**, DB transactions/constraints, lease timeouts when a worker crashes, retry budgets, and how to distinguish “sent but crashed before recording SUCCEEDED”.

**Do not promise exactly-once via locking alone:** a worker can call an external API successfully and then crash before committing the status. A retry may send it again; you need idempotency or business logic tolerant of at-least-once delivery.

### 11.4. When to Choose Quartz or a Job Queue?

- **Simple one-shot, acceptable to lose on restart, no multiple replicas:** `ThreadPoolTaskScheduler` is sufficient.
- **Schedules that must be persisted and recovered:** consider Quartz with a properly configured JDBC job store, or a job table + worker mechanism with durable claiming.
- **Need retries, dead-lettering, multi-step workflows:** a message broker / job queue / workflow engine is better suited than an in-memory `ScheduledFuture`.
- **Running multi-node:** ensure coordination in the job store or distribution layer; do not treat a single `TaskScheduler` instance as a distributed lock.

Quartz does not automatically solve everything either: you must choose the job store/persistence, configure clustering/locking, misfire handling, concurrency, recovery, and proper idempotent business logic.

## 12. When to Use Clock and How to Test Time?

The `TaskScheduler.getClock()` API allows working with the scheduler's clock. `ThreadPoolTaskScheduler.setClock(Clock)` supports specifying the clock source used for time calculations. This helps with testing/time interpretation, **but does not turn the executor into a fully virtual time controller**: the underlying scheduler still relies on real delay/timing mechanisms.

### Decoupling Time Calculation from Execution

For fast and deterministic tests, separate the logic:

1. Parse/validate user-entered time, time zone, and business rules.
2. Compute `Instant scheduledAt` from an injected `Clock`.
3. Call a `TaskScheduler` interface (which can be mocked/spied) with the exact `Runnable` and `Instant`.
4. In a separate integration test, use a real scheduler and `Future.get(timeout)`/latch to verify the callback executes.

Method snippet with Clock:

```java
public Instant nextFireTime(Clock clock, Duration delay) {
    if (delay.isNegative()) {
        throw new IllegalArgumentException("delay must not be negative");
    }
    return clock.instant().plus(delay);
}
```

This is a method-body snippet requiring imports for `Clock`, `Duration`, and `Instant`. With `Clock.fixed(...)` in unit tests, the computed result is completely deterministic; there is no need to sleep for minutes.

**Do not fix a clock and expect a real executor to jump into the future automatically.** `ThreadPoolTaskScheduler` still computes delays from the configured clock's current time at scheduling and relies on the actual worker/timer to execute. For an already-submitted schedule, changing the system clock afterward does not necessarily shift wall-clock execution time as you might expect.

### How to Test One-Shots with a Real Scheduler

- Use a short future mark and `Future.get(timeout)` or `CountDownLatch.await(timeout)`.
- Verify counter == 1 after the Future completes.
- Test cancellation while the task is definitely still far in the future.
- Test `TaskRejectedException` handling when the scheduler has shut down in a dedicated test.
- Test callback failure via `ExecutionException` and logging/status at the business boundary.
- Verify no second execution occurs, without relying on `Thread.sleep(5s)` to “prove it never repeats forever”: the one-shot contract + completed Future + counter is the appropriate evidence.
- For time-zone features, unit-test DST gaps/overlaps along with `LocalDateTime`-to-`Instant` conversion.
- For persistence, test restarts/crashes, duplicate claiming, and retry/idempotency rather than only unit-testing the scheduler.

## 13. Common Mistakes and Fixes

### Mistake 1: Using LocalDateTime as an Absolute Point in Time

`LocalDateTime` has no time zone. Use an explicit `ZoneId` and convert to `Instant`; do not rely on the server's default timezone. Watch out for DST gaps/overlaps.

### Mistake 2: Thinking schedule() Creates a Recurring Schedule

`schedule(Runnable, Instant)` is one-shot. To repeat, use Trigger/fixed-rate/fixed-delay; do not assume a single run will be re-created by the scheduler.

### Mistake 3: Treating Instant as a Millisecond-Exact Promise

A task becoming due is different from a worker starting it. A slow task can delay other tasks; measure scheduling lag and set capacity/deadlines.

### Mistake 4: Waiting on ScheduledFuture.get() in an HTTP Request for Hours

The caller can stay blocked until the job finishes, leading to timeouts and tied-up request threads/connections. Return a job ID / accepted response; track results via status/events instead of blocking the request.

### Mistake 5: Instantiating new ThreadPoolTaskScheduler per Request

Each instance has its own thread pool/lifecycle; doing so inflates resource usage and makes proper shutdown hard. Use a managed singleton Spring bean, or a scheduler with a clear owner/lifecycle.

### Mistake 6: Failing to Initialize the Scheduler in Standalone Programs

If you manually create `new ThreadPoolTaskScheduler()` outside a Spring container, you must call `initialize()` before `schedule()`; shut it down when done. With standard beans, Spring manages the lifecycle.

### Mistake 7: Forgetting to Handle Cancelled or Failed Jobs

`isDone()` can be true on failure/cancellation, not only on success. With a Future, check `isCancelled()` and `get()`; for critical business tasks, keep dedicated status/metrics.

### Mistake 8: Assuming cancel(true) Reverts All Side Effects

An interrupt does not forcibly stop remote HTTP/DB calls or roll back committed transactions. Use cancellation-aware APIs, timeouts, and idempotency.

### Mistake 9: Assuming @EnableScheduling Is Required for Programmatic schedule()

With a managed `TaskScheduler` bean, calling `schedule(...)` directly does not require `@EnableScheduling`. That annotation is for the infrastructure that processes `@Scheduled`. Do not mix the two mechanisms and lose track of where jobs are registered.

### Mistake 10: Storing ScheduledFuture in a Static Map and Calling It Persistent Scheduling

Maps and handles only exist inside the JVM. Restarts lose everything, and multiple pods have separate maps. If schedules must survive deploys/restarts, use durable storage and a recovery mechanism.

### Mistake 11: Multiple Pods Running the Same Task

A local schedule provides no cluster-wide guarantee. Use proper atomic claiming / distributed coordination and handle duplicates with idempotency.

### Mistake 12: Submitting Heavy Runnables to a Single-Thread Scheduler Pool

`ThreadPoolTaskScheduler` runs tasks on the scheduler thread. Long blocking work delays other due jobs. Grow the pool carefully or offload heavy work to a worker executor with explicit tracking/rejection handling.

### Mistake 13: Automatically Retrying Every Error with a New schedule() Unboundedly

If a job fails and loops infinitely by re-registering itself after 100 ms, backlog can grow and cause a retry storm. You need a retry budget, exponential backoff/jitter, a stable job ID, and idempotency.

### Mistake 14: Ignoring Past Times

Per the API, past times run as soon as possible; however, the product may want to reject them or mark them missed. Define explicit user-facing behavior, especially for time-sensitive reminders/contracts.

## 14. Production Readiness Checklist

Before deploying a one-shot scheduling feature:

1. **Define the timestamp:** does input include timezone/offset? Is DST involved? Store `Instant` or also the original timezone?
2. **Define acceptable precision:** is 1 second or 1 minute of lag acceptable, or is delay forbidden? Is there a missed/deadline policy?
3. **Choose the lifecycle:** is the schedule only needed while the JVM is alive, or must it survive restarts?
4. **Determine instance count:** single JVM or multiple pods? Can the job run twice?
5. **Pick the right API:** `schedule(Runnable, Instant)` for once; do not use periodic APIs if repetition is unintended.
6. **Bound capacity:** scheduler pool size, blocking work, DB/HTTP connections, downstream quotas, and backlog.
7. **Manage handles:** is there a job ID, cancel mechanism, status, and user authorization to cancel?
8. **Distinguish errors:** schedule rejection at caller, callback failure in worker, future cancellation, and timeout when a caller waits.
9. **Ensure cleanup:** scheduler lifecycle, shutdown, cancellation; do not leave unclosed thread pools.
10. **Observe:** start lag, run duration, success/failure/cancel counts, missed deadlines, and queue depth.
11. **Test:** runnable example, future/past times, multiple jobs due together, restarts, multiple instances, duplicates, and idempotency.
12. **Ensure business guarantees:** if “run exactly once” is needed in terms of business impact, design a job store and idempotency; the one-shot API only bounds scheduling **within one scheduler instance**.

### Quick Selection Table

| Requirement | Usually Suitable Mechanism | Limitation to Remember |
| --- | --- | --- |
| Once after a few seconds in a live JVM | `TaskScheduler.schedule(Runnable, Instant)` | Not durable across restarts |
| Once at a specific user wall-clock time | Convert `LocalDateTime + ZoneId → Instant`, then `schedule` | Must handle timezones/DST |
| Repeating every interval | `scheduleAtFixedRate` / `scheduleWithFixedDelay` | Not one-shot |
| By cron/timezone | `Trigger`/Cron or dedicated scheduler | DST, misfires, job lifecycle |
| Many schedules spanning days, needing recovery | Persistent job store / Quartz JDBC | Requires clustering, retries, and idempotency |
| Schedule a timer then offload heavy work | One-shot schedule submitting to a bounded executor | Schedule's Future may track only submission |
| Cancel an unexecuted schedule | Keep `ScheduledFuture` and call `cancel(false)` | Local to JVM, not durable |
| Pods must not process duplicates | Durable claiming/coordination | Not built into local TaskScheduler |

## 15. Summary and Official Documentation

**Eight key points:**

1. `TaskScheduler.schedule(Runnable, Instant)` registers a job to run **once** at or after the specified time.
2. `Instant` is an absolute point in time; convert from local date/time using `ZoneId` before scheduling.
3. If the time is in the past, the API schedules it to run **as soon as possible**, without automatically dropping the task.
4. `ScheduledFuture<?>` is the handle for tracking completion/cancellation; `get()` can block and should not be called in HTTP requests just to wait on a long-term schedule.
5. `ThreadPoolTaskScheduler` runs tasks on the scheduler threads themselves, with a default pool size of 1; long tasks can delay other schedules.
6. Errors from `schedule(...)` on rejection differ from errors occurring inside `Runnable.run()`.
7. Cancellation/shutdown does **not** mean rolling back side effects already applied to databases or remote systems.
8. For schedules to survive restarts or execute on only one instance in a cluster, persistence, claiming/idempotency, and coordination outside a single local scheduler are required.

**Official Documentation:**

- [Spring Framework 6.2 – TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/TaskScheduler.html) — `schedule(Runnable, Instant)`, past-time handling, and `TaskRejectedException`.
- [Spring Framework 6.2 – ThreadPoolTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html) — pool size, scheduling, lifecycle, error handler, and removal/cancellation policies.
- [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html) — using the abstraction and scheduler types.
- [Java SE 17 – ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html) — `getDelay`, `cancel`, `get`, and completion states.
- [Java SE 17 – ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html) — scheduled queue, worker pool, and remove-on-cancel.
- [Java SE 17 – Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — absolute points in time.
- [Java SE 17 – ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html) — time zone conversions and daylight saving rules.

**Conclusion:** `schedule(task, instant)` is a clear choice to **run once at a desired time** in a live Spring scheduler. Use `ScheduledFuture` to manage local schedules, monitor actual lag, and proactively design persistence/cluster coordination if this is a critical business requirement that must not be lost during deployments or restarts.
