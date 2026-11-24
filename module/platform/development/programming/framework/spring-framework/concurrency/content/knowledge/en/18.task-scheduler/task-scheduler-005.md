# ScheduledFuture for Tracking and Cancelling Schedules

## 1. Why Does a TaskScheduler Need to Return ScheduledFuture?

In Spring Framework, `TaskScheduler` lets you schedule a `Runnable` task: run once at a specific time, repeat at a fixed rate, repeat after a pause from the previous run, or run according to a `Trigger` such as cron.

Once a task is registered, the application often needs to **track status and proactively cancel the schedule**: a user disables a recurring report, frequency configuration changes, a tenant stops using the service, a resource is released, or a pending job is no longer relevant.

Programmatic scheduling methods on `TaskScheduler` typically return:

```java
java.util.concurrent.ScheduledFuture<?>
```

This is a **handle to the scheduled task**. It is not a database job identifier, not a durable cron record, and does not by itself guarantee the task has finished. However, it exposes essential APIs:

- `cancel(boolean mayInterruptIfRunning)`: requests cancellation of the schedule.
- `isCancelled()`: checks whether the handle is in the cancelled state.
- `isDone()`: checks whether the Future has reached a terminal state.
- `getDelay(TimeUnit unit)`: estimates the remaining delay until the relevant trigger time.
- `get()` or `get(timeout, unit)`: waits for a Future to complete; **you must distinguish one-shot tasks from recurring tasks**.

Conceptual example:

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::refreshCache,
        Duration.ofMinutes(5)
);

// When you do not want subsequent runs:
boolean accepted = handle.cancel(false);
```

This is a **code snippet inside a class that has `scheduler` and `refreshCache()`**, not a standalone program. `cancel(false)` does not force an already-started run to stop immediately; it expresses intent to cancel the schedule without requesting interruption of the executing thread.

**Lesson objectives:** understand how `ScheduledFuture` relates to `TaskScheduler`, read states accurately, cancel one-shot/periodic/trigger tasks, distinguish `cancel(false)` and `cancel(true)`, manage multiple handles safely, handle errors and Spring lifecycle, with a Java 17 example producing verifiable output.

## 2. Relationship Diagram: TaskScheduler → ScheduledFuture → Schedule Lifecycle

```text
Application / service
       |
       | scheduler.schedule*(Runnable, ...)
       v
    TaskScheduler
       |
       +--- accepts task, computes run time
       |
       +--- returns ScheduledFuture<?> to caller
       |                       |
       |                       +-- getDelay(...)
       |                       +-- isDone()
       |                       +-- isCancelled()
       |                       +-- cancel(false/true)
       v
Scheduled executor / Trigger
       |
       +--- not yet due --> stays in waiting structure
       |
       +--- due --> worker runs Runnable
       |                   |
       |                   +--- one-shot: completes Future
       |                   |
       |                   +--- periodic: may schedule next run
       |
       +--- cancel / shutdown / terminal failure
```

**A schedule is a coordination object**, whereas each `Runnable` invocation is one execution run. A handle for a recurring job can remain “not done” even after the task has succeeded hundreds of times, because the schedule persists until cancelled or terminated abnormally.

In traditional `ThreadPoolTaskScheduler`, Spring uses a Java `ScheduledThreadPoolExecutor` and tasks execute on the scheduler thread(s). That differs from a “scheduler merely wakes a secondary executor” model in other implementations. Thus **the time a task holds the worker** directly affects execution capacity for other schedules. Do not assume all `TaskScheduler` implementations share the same thread strategy or error-management semantics.

## 3. What Methods Does ScheduledFuture Have?

`ScheduledFuture<V>` lives in `java.util.concurrent` and **extends `Delayed` and `Future<V>`**. Thus it has two API groups.

| API | Source | Meaning |
|---|---|---|
| `getDelay(TimeUnit)` | `Delayed` | Estimated remaining time before the task becomes eligible to fire |
| `compareTo(Delayed)` | `Delayed`/`Comparable` | Compares delays per contract |
| `cancel(false)` | `Future` | Cancels without requesting interruption of an in-flight run |
| `cancel(true)` | `Future` | Cancels and permits attempting to interrupt the thread if running |
| `isCancelled()` | `Future` | Whether the Future was cancelled |
| `isDone()` | `Future` | Whether the Future ended normally, with an error, or via cancellation |
| `get()` | `Future` | Waits for completion and retrieves result/exception |
| `get(timeout, unit)` | `Future` | Waits boundedly and may throw `TimeoutException` |

Commonly misunderstood rules:

1. **`isDone() == true` does not mean “succeeded”**. It is also true when the Future was cancelled or completed exceptionally.
2. **`isCancelled() == true` does not prove code inside an in-flight run has stopped completely**. With `cancel(false)`, the executing run can continue to completion.
3. **`getDelay(...)` is not an absolute timestamp of the next run** and not a progress percentage. The value can change right after reading; if past due, it may be zero or negative depending on implementation.
4. **`ScheduledFuture<?>` carries no business return value from a `Runnable`**. For a one-shot `Runnable` completing normally in Java `ScheduledExecutorService`, `get()` returns `null`; Spring `TaskScheduler` does not turn it into a custom computed value either.
5. For a **live recurring schedule**, `get()` does not mean “wait for one run to finish”. It typically waits until the entire execution series terminates—which may only happen on cancellation or failure.

### 3.1. Status of One Run Is Not Status of the Whole Schedule

For example, cron runs at 01:00 daily; today's run finished. If tomorrow's schedule remains active:

```text
One run today: SUCCEEDED
Schedule's ScheduledFuture: still ACTIVE / isDone() usually false
Next run: tomorrow 01:00
```

Do not use `isDone()` to conclude “did today's job finish?”. To track individual runs, record `lastStartedAt`, `lastCompletedAt`, `lastSucceededAt`, run counts, errors, and state in your own model.

## 4. TaskScheduler Methods Returning Handles

In Spring Framework 6.x, `TaskScheduler` provides overloads based on `Instant`/`Duration` and `Trigger`. Representative signatures:

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);

@Nullable
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

This is a **summary of Spring API signatures**, not a standalone interface to compile on its own. `Trigger` is `org.springframework.scheduling.Trigger`, while `ScheduledFuture` belongs to Java. In Spring 6.x, many older `Date`/`long` overloads are deprecated; prefer `Instant` and `Duration` in new code.

### 4.1. Run Once at a Specified Time

```java
ScheduledFuture<?> once = scheduler.schedule(
        () -> publishReport(reportId),
        Instant.now().plusSeconds(30));
```

This is a business snippet; `scheduler` is a `TaskScheduler`, while `publishReport` and `reportId` are supplied by the application. The **one-shot** task runs at the appropriate time and the Future completes after that run (or upon cancellation/error).

### 4.2. Fixed Rate — Target Interval Between Start Times

```java
ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
        this::pollStatus,
        Duration.ofSeconds(10));
```

With fixed rate, the schedule tries to maintain start times on the configured period. If one run lasts longer than the period, the next run may start late; in Java's `ScheduledThreadPoolExecutor`, runs **of the same periodic task** do not execute concurrently. This does not forbid two **different jobs** from running concurrently on different workers.

### 4.3. Fixed Delay — Waiting After the Previous Run Completes

```java
ScheduledFuture<?> periodic = scheduler.scheduleWithFixedDelay(
        this::cleanup,
        Duration.ofSeconds(10));
```

Fixed delay counts the pause between the **end of one run** and the **start of the next run**. If `cleanup` takes 30 seconds, the gap between two start times is greater than 10 seconds. For jobs with variable execution duration that do not need to hug wall-clock marks, fixed delay is often easier to control than fixed rate.

### 4.4. Trigger/Cron — Dynamically Computed Times

```java
import org.springframework.scheduling.support.CronTrigger;

ScheduledFuture<?> cron = scheduler.schedule(
        () -> refreshIndexes(),
        new CronTrigger("0 */5 * * * *"));
```

This illustrative snippet runs every 5 minutes per Spring's 6-field cron expression (`second minute hour day month day-of-week`). When using local time / business time zones, configure an appropriate timezone/clock and check DST behavior.

**Special note:** `schedule(Runnable, Trigger)` **can return `null`** if the trigger yields no next execution time (`Trigger.nextExecution(...)` returns `null`). Therefore:

```java
ScheduledFuture<?> handle = scheduler.schedule(work, trigger);

if (handle == null) {
    // No execution will be triggered.
} else {
    // Handle can be managed.
}
```

A `null` here is not the same as a cancelled `Future`; it means **no schedule was registered at call time**. For `Instant` and `Duration` overloads, the return contract is a non-nullable `ScheduledFuture<?>` on standard `TaskScheduler`.

## 5. cancel(false) and cancel(true): Understanding mayInterruptIfRunning Properly

`cancel(boolean mayInterruptIfRunning)` requests cancelling the Future. The two calls differ primarily in **what happens if a run has already started**:

| Call | Typical Use Case | Effect on In-Flight Run |
|---|---|---|
| `cancel(false)` | Stop **subsequent** runs, let current run finish on its own | Does not request interrupting the executing thread |
| `cancel(true)` | Try to stop early if running work supports interruption | May interrupt worker; does not guarantee immediate stop for all tasks |

**Do not interpret `cancel(false)` as “wait for the current run to finish”.** It does not wait. Immediately after the method returns, an in-flight run may still be using CPU, I/O, connections, or touching external systems.

`cancel(true)` is not a forced “kill thread” command either. Interruption in Java is a cooperative mechanism:

- `Thread.sleep`/`BlockingQueue.take`/`CountDownLatch.await` and many blocking calls can react with `InterruptedException`.
- CPU computations in long loops only stop if code checks the interrupted flag or a custom cancellation mechanism.
- Many I/O operations and third-party APIs respond differently to interruption; library-specific timeouts and cancellation hooks are needed.
- If the task already performed a side effect, `cancel(true)` does not roll back emails, payments, database rows, or HTTP commands.

### 5.1. Reading the Boolean Return Value of cancel

`boolean accepted = handle.cancel(false)` generally indicates **the Future cancellation request was accepted**; it is not a receipt proving the worker stopped running. `cancel(...)` can return `false` if the Future already completed or cannot be cancelled per implementation. When multiple callers cancel concurrently, one may observe `true` and another `false`.

If you need the final state, check `isCancelled()` and track separately when the task has actually exited execution. When cancelling to stop a service, use a dedicated shutdown/drain mechanism; do not treat one Future flag as proof that all resources have been released.

### 5.2. Pattern for Handling Interruption in Runnable

```java
Runnable cancellable = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doSmallUnitOfWork();
            Thread.sleep(100);
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        // Finish the task so the outer loop does not keep running.
    } finally {
        releaseOwnedResources();
    }
};
```

This is an illustrative snippet; `doSmallUnitOfWork` and `releaseOwnedResources` must be defined by the application. Code must be designed so `doSmallUnitOfWork()` itself does not run forever. In `finally`, release only resources actually owned by the task; do not close the application's shared scheduler.

## 6. isDone/isCancelled: State Table to Remember

| Scenario | `isDone()` | `isCancelled()` | Explanation |
|---|---|---|---|
| One-shot accepted, not yet due | Usually `false` | `false` | Still waiting for scheduled time |
| One-shot currently executing | Usually `false` | `false` | Future not yet complete |
| One-shot finished normally | `true` | `false` | Terminated successfully |
| One-shot ran and threw propagated exception | `true` | `false` | Terminated with failure |
| Future successfully cancelled | `true` | `true` | Terminal state is cancelled |
| Periodic still active across many runs | Usually `false` | `false` | Whole schedule series remains active |
| Periodic stopped due to propagated error | Can be `true` | `false` | Depends on scheduler error policy |
| Spring periodic with default log/suppress errors | Usually still `false` | `false` | Series can continue after a single-run error |

**Watch out for Spring's default:** traditional `ThreadPoolTaskScheduler` wraps tasks using `TaskUtils`. By default, exceptions from **repeating** tasks are usually **logged and suppressed** so the schedule has a chance to run subsequent iterations; **one-shot** tasks are usually logged and propagated so callers can observe errors via Future. Therefore you cannot copy raw Java `ScheduledThreadPoolExecutor`'s conclusion that one exception in a periodic runnable always terminates the schedule. Check the `ErrorHandler` of the scheduler in use.

## 7. A Pure Java 17 Program Proving Cancellation

`ScheduledFuture` is a standard Java API, so core states can be verified **without Spring**. The example below schedules a task one day out, cancels it before it runs, and checks status and `get()` behavior.

**File `ScheduledFutureCancelDemo.java` — standalone on JDK 17:**

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ScheduledFutureCancelDemo {
    public static void main(String[] args) {
        ScheduledThreadPoolExecutor executor =
                new ScheduledThreadPoolExecutor(1);
        executor.setRemoveOnCancelPolicy(true);
        AtomicInteger executions = new AtomicInteger();

        try {
            ScheduledFuture<?> handle = executor.schedule(
                    executions::incrementAndGet,
                    1, TimeUnit.DAYS);

            System.out.println("Still delayed: "
                    + (handle.getDelay(TimeUnit.SECONDS) > 0));

            System.out.println("Cancelled successfully: " + handle.cancel(false));
            System.out.println("Is cancelled: " + handle.isCancelled());
            System.out.println("Is done: " + handle.isDone());

            try {
                handle.get();
            } catch (CancellationException expected) {
                System.out.println("get(): CancellationException");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(interrupted);
            } catch (java.util.concurrent.ExecutionException failure) {
                throw new IllegalStateException(failure);
            }

            System.out.println("Execution count: " + executions.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac ScheduledFutureCancelDemo.java
java ScheduledFutureCancelDemo
```

Output under normal wall-clock conditions:

```text
Still delayed: true
Cancelled successfully: true
Is cancelled: true
Is done: true
get(): CancellationException
Execution count: 0
```

Why is the output deterministic? The schedule is set one day ahead and cancelled immediately on the same thread before coming due. `cancel(false)` marks the Future cancelled, `get()` throws `CancellationException` instead of waiting a day, and `executions` was never incremented. On a machine frozen for over a day or with abnormal system clocks, delay output could no longer be guaranteed; the example intentionally uses a large delay to demonstrate normal operation.

**`setRemoveOnCancelPolicy(true)`** instructs `ScheduledThreadPoolExecutor` to evict cancelled tasks from the queue promptly rather than retaining them until their delay expires. This is a queue-management option; it **does not alter `cancel(false)` semantics** and does not undo completed business work.

## 8. One-Shot vs. Recurring: How to Use get()?

### 8.1. One-Shot Runnable

For a one-time schedule, `get(timeout)` can be used to wait for completion (or detect failure). A `Runnable` returns no business value; on normal completion, `get()` returns `null` per `ScheduledExecutorService`'s contract.

```java
ScheduledFuture<?> future = scheduler.schedule(
        () -> generateDailySnapshot(),
        Instant.now());

try {
    Object value = future.get(10, TimeUnit.SECONDS);
    // value is usually null when Runnable completes normally.
} catch (TimeoutException timeout) {
    future.cancel(true);
}
```

This snippet belongs inside a method with `scheduler`/`generateDailySnapshot` and the corresponding Java imports; the method must also handle `InterruptedException` and `ExecutionException` or declare `throws`. `get(timeout)` blocks the caller until the Future completes or the wait expires. **Timing out does not auto-cancel**: call `cancel(...)` explicitly if appropriate, then handle deadlines and business side effects.

### 8.2. Periodic Runnable

For an active repeating job, **do not call `get()` to “wait for the latest cron run to finish”**. The Future represents the series, so the call can block indefinitely while the schedule runs normally. In Java `ScheduledExecutorService`, `get()` on a periodic Future never returns normally; it only exits via cancellation, error, or interruption per contract.

An anti-pattern:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        this::refresh, Duration.ofMinutes(1));
future.get(); // Can wait forever while the schedule keeps running.
```

This is an **anti-pattern snippet**; do not use it on HTTP threads or startup paths without an explicit stop plan. In Spring, the default `ErrorHandler` may suppress recurring errors, keeping the Future alive even when a run fails.

If you need to know whether **the latest run** finished, record it separately: an `AtomicInteger` run counter, a `CountDownLatch` for a specific test milestone, a per-run `CompletableFuture` if your API is designed that way, or persist `lastExecutionStatus` in a controlled state store.

## 9. Using ScheduledFuture in Spring ThreadPoolTaskScheduler

`ThreadPoolTaskScheduler` is the standard implementation of Spring `TaskScheduler`, backed by `ScheduledThreadPoolExecutor`. It offers `setPoolSize(...)`, `setThreadNamePrefix(...)`, `setErrorHandler(...)`, `setRemoveOnCancelPolicy(...)`, and lifecycle/shutdown options.

**File `SchedulerConfig.java` — Spring Configuration, not standalone:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class SchedulerConfig {

    @Bean("jobScheduler")
    public ThreadPoolTaskScheduler jobScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("job-clock-");
        scheduler.setRemoveOnCancelPolicy(true);

        return scheduler;
    }
}
```

Spring manages initialization and shutdown of this bean per `ApplicationContext`. A service injecting the bean:

```java
import java.time.Duration;
import java.util.concurrent.ScheduledFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class AuditScheduleService {
    private final TaskScheduler scheduler;

    public AuditScheduleService(
            @Qualifier("jobScheduler") TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public ScheduledFuture<?> start() {
        return scheduler.scheduleWithFixedDelay(
                () -> System.out.println("audit tick"),
                Duration.ofMinutes(2));
    }
}
```

This is a **Spring component**, not a standalone Java SE program. In production, **retain the returned handle** if you want to cancel the schedule you created; if `start()` creates a new schedule on every request with nobody owning the handle, the application can accumulate duplicate schedules with no clean way to manage them.

**`@EnableScheduling` is not needed for direct programmatic `scheduler.schedule*(...)` calls.** `@EnableScheduling` mainly enables processing of `@Scheduled` annotations; that is a different registration mechanism. Even so, an application may use both simultaneously.

### 9.1. Designing Handles Around Business Lifecycle

A service receiving “enable/disable schedule for report-X” commands needs to store a handle per report ID rather than a single shared field:

```text
Report-A  -> ScheduledFuture-A
Report-B  -> ScheduledFuture-B
Report-C  -> ScheduledFuture-C
```

If a client wants to turn off `Report-B`, the service looks up B's handle and calls `cancel(...)` on that exact object. A `ScheduledFuture` is only valid inside the process/container that created the schedule. It is not an ID you can send externally for another JVM to look up the Future, and it does not survive application restarts.

## 10. Complete Maven Example: One-Shot Execution, Cancelling a Periodic Schedule, and Cancelling a Pending Schedule

The following example uses **JDK 17+**, Maven, and **Spring Framework 6.2.7**. It demonstrates that the same `ThreadPoolTaskScheduler` can:

1. Run a `Runnable` once, then call `get(...)` expecting `null`.
2. Run a fixed-delay schedule with a very long delay, wait for the first run via `CountDownLatch`, and then call `cancel(false)` to prevent subsequent runs.
3. Register a job one hour in the future and cancel it before it runs.

The reason for using a long delay and a latch is to obtain **verifiable stdout without relying on `Thread.sleep` or worker races**.

### 10.1. Directory Structure

```text
scheduled-handle-demo/
├── pom.xml
└── src/main/java/lesson/ScheduledHandleDemo.java
```

### 10.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>scheduled-handle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. File src/main/java/lesson/ScheduledHandleDemo.java

```java
package lesson;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class ScheduledHandleDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskScheduler scheduler = context.getBean(
                    "demoScheduler", TaskScheduler.class);

            AtomicInteger onceCount = new AtomicInteger();
            ScheduledFuture<?> once = scheduler.schedule(
                    onceCount::incrementAndGet,
                    Instant.now());

            Object oneResult = once.get(5, TimeUnit.SECONDS);
            System.out.println("One-shot done: " + once.isDone());
            System.out.println("Runnable result is null: "
                    + (oneResult == null));
            System.out.println("One-shot runs: "
                    + onceCount.get());

            CountDownLatch firstTick = new CountDownLatch(1);
            AtomicInteger tickCount = new AtomicInteger();

            ScheduledFuture<?> recurring =
                    scheduler.scheduleWithFixedDelay(() -> {
                        tickCount.incrementAndGet();
                        firstTick.countDown();
                    }, Duration.ofHours(1));

            if (!firstTick.await(5, TimeUnit.SECONDS)) {
                recurring.cancel(true);
                throw new IllegalStateException("Missing first run");
            }

            System.out.println("Cancel recurring schedule: "
                    + recurring.cancel(false));
            System.out.println("Recurring schedule cancelled: "
                    + recurring.isCancelled());
            System.out.println("Runs executed: "
                    + tickCount.get());

            AtomicInteger lateRuns = new AtomicInteger();
            ScheduledFuture<?> later = scheduler.schedule(
                    lateRuns::incrementAndGet,
                    Instant.now().plus(Duration.ofHours(1)));

            System.out.println("Cancel pending schedule: "
                    + later.cancel(false));
            System.out.println("Pending schedule runs: "
                    + lateRuns.get());
        }
    }

    @Configuration
    public static class Config {
        @Bean("demoScheduler")
        public ThreadPoolTaskScheduler demoScheduler() {
            ThreadPoolTaskScheduler scheduler =
                    new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(2);
            scheduler.setThreadNamePrefix("schedule-demo-");
            scheduler.setRemoveOnCancelPolicy(true);
            return scheduler;
        }
    }
}
```

### 10.4. Compile and Run

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.ScheduledHandleDemo
```

**Eight lines printed by the program in a normal run environment:**

```text
One-shot done: true
Runnable result is null: true
One-shot runs: 1
Cancel recurring schedule: true
Recurring schedule cancelled: true
Runs executed: 1
Cancel pending schedule: true
Pending schedule runs: 0
```

These lines are printed by the program's `println` statements, excluding Maven/Spring's own logs. The 5-second timeout makes the program fail explicitly if workers cannot execute in time on an overloaded machine, rather than hanging indefinitely.

Why is it deterministic:

- `once.get(5, TimeUnit.SECONDS)` waits for the one-shot task to finish; `Runnable` returns no value so `oneResult` is `null`, while `onceCount` is 1.
- `scheduleWithFixedDelay(..., Duration.ofHours(1))` lets the first run execute right away; `firstTick.await` confirms it incremented and signaled the latch. The next run only arrives **one hour after the previous run finishes**.
- `recurring.cancel(false)` requests terminating the periodic series without interrupting the worker. Because future runs remain, the Future did not complete normally after the first run.
- `later` is a one-shot schedule one hour out, cancelled before coming due. Thus `lateRuns` is 0 when printed.
- `try-with-resources` closes the Spring context, leaving scheduler bean shutdown to Spring; a service does not shut down a shared scheduler on its own.

This example illustrates **the handle and cancellation contract**, not how to build a durable job system. The worker count of 2, 1-hour duration, and timeouts are chosen for illustration, not as production recommendations.

## 11. Avoid the Misconception: cancel(false) Does Not Wait for the Current Run to Finish

Imagine a running task:

```text
T=0s       worker starts sending large file
T=1s       caller invokes future.cancel(false)
T=1.001s   future.isCancelled() can be true
T=10s      worker finishes sending file and releases connection
```

`cancel(false)` can mark the schedule cancelled at T=1s to prevent the next iteration, yet **does not forcibly stop the active run**. If job-management code immediately deletes all state and frees shared resources at T=1.001s, the worker may still access those resources and cause a race.

A stop protocol usually needs **two phases**:

1. **Stop scheduling new runs**: hold the handle and cancel the schedule, usually with `cancel(false)` for graceful behavior.
2. **Wait for / observe active runs finishing**: use a `CountDownLatch`, `Phaser`, active counter, job status, or shutdown/await termination at the appropriate resource level.

Do not call `future.get()` on a periodic schedule to wait for an already-started run because it tracks **the entire series**. For I/O tasks, add timeouts and dedicated cancellation/reconciliation policies.

## 12. When Should You Use cancel(true)?

An appropriate case is a task that supports interruption, where work can be aborted mid-way without leaving dangerous half-finished side effects.

```java
Runnable job = () -> {
    try {
        for (int i = 0; i < 100; i++) {
            if (Thread.currentThread().isInterrupted()) {
                return;
            }
            performSmallBatch(i);
        }
    } finally {
        closeOwnedResources();
    }
};
```

This is an **illustrative snippet**, with `performSmallBatch`/`closeOwnedResources` belonging to the application. Callers can request `handle.cancel(true)`; the task must deliberately check interrupted status while ensuring resources are released.

If each batch writes to the database and commits incrementally, interruption does not roll back earlier batches. Therefore cancelling an important job requires statuses like `CANCEL_REQUESTED`, `CANCELLED`, `PARTIAL`, or equivalent if business rules demand it; do not equate the Future flag with the final business outcome.

**Caution:** Some libraries use interruption for internal coordination. Read their contracts before interrupting a shared scheduler's worker, especially when tasks involve callbacks or shared resources.

## 13. Managing Multiple Schedules in a Service via a Handle Registry

If users can enable/disable multiple schedules, holding just one `ScheduledFuture<?> last` field is impossible. A simple approach within **one JVM** is a map from job ID to handle.

**File `ManagedScheduleService.java` — illustrative Spring-managed component:**

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ScheduledFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class ManagedScheduleService {

    private final TaskScheduler scheduler;
    private final Map<String, ScheduledFuture<?>> handles =
            new HashMap<>();

    public ManagedScheduleService(
            @Qualifier("jobScheduler") TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public synchronized void replace(
            String jobId, Runnable work, Duration delay) {

        Objects.requireNonNull(jobId);
        Objects.requireNonNull(work);
        if (delay.isZero() || delay.isNegative()) {
            throw new IllegalArgumentException(
                    "Delay must be positive");
        }

        ScheduledFuture<?> fresh =
                scheduler.scheduleWithFixedDelay(work, delay);

        ScheduledFuture<?> previous = handles.put(jobId, fresh);
        if (previous != null) {
            previous.cancel(false);
        }
    }

    public synchronized boolean stop(String jobId) {
        ScheduledFuture<?> handle = handles.remove(jobId);
        return handle != null && handle.cancel(false);
    }

    public synchronized boolean isRegistered(String jobId) {
        return handles.containsKey(jobId);
    }
}
```

This is a **Spring class**, with no standalone `main`. The `synchronized` lock protects map operations when concurrent requests invoke `replace/stop` in the same instance. It does **not** hold the lock while `work` runs; business execution happens on the scheduler outside the lock.

The limitations of this pattern must be stated clearly:

- `scheduleWithFixedDelay` can run its first iteration **very early**. Thus during replacement, for a brief window both `fresh` and the old run may coexist/run concurrently before `previous.cancel(false)` takes effect.
- `cancel(false)` on the old schedule does not interrupt an executing old run. If side effects of two job versions must never overlap, business-level serialization/leasing/idempotency is needed.
- `isRegistered` only tells whether the map holds a handle, not that the schedule is still alive. You can add checks for `isCancelled`/`isDone` or a stricter status registry.
- If `scheduleWithFixedDelay` is rejected, the method throws an exception before updating the map, so the old handle stays intact. Handle submission errors at the API boundary.
- The map and Futures live only within **one process**. Running multiple pods yields separate registries; there is no leader election or cross-pod cancellation synchronization here.
- Do not leave finished one-shot `ScheduledFuture` instances in the map forever; clean up unused entries to avoid retaining references and resources.
- Using `HashMap + synchronized` illustrates managing a small registry. Under heavy load, multi-state lifecycles, or cluster requirements, build a dedicated abstraction and test it under concurrency.

### 13.1. Cancellation API by Job ID

A controller can call `managedScheduleService.stop(jobId)` to submit a cancellation request. The HTTP response should reflect **whether the local scheduler accepted the cancellation request**, not claim that all side effects stopped instantaneously.

If users need to know when stopping fully completes, the API typically needs job state and reconciliation with any active run. For distributed systems, a job ID should live in durable storage linked to a scheduler owner/lease instead of exposing `ScheduledFuture` directly to clients.

## 14. CronTrigger and the Case of No Next Schedule

`TaskScheduler.schedule(Runnable, Trigger)` can return `null` when `Trigger.nextExecution(...)` yields no time—for instance, a `Trigger` with a run-count cap or one whose business condition is no longer met.

```java
import java.util.concurrent.ScheduledFuture;
import org.springframework.scheduling.Trigger;

public ScheduledFuture<?> register(
        Runnable work, Trigger trigger) {
    return scheduler.schedule(work, trigger);
}
```

This is an illustrative method inside a class holding `scheduler`. The API can return `null`, so callers should check:

```java
ScheduledFuture<?> handle = register(work, trigger);
if (handle == null) {
    System.out.println("No next schedule");
} else {
    saveHandle(handle);
}
```

Never call `handle.cancel(false)` when `handle == null`. Also, `getDelay(...)` on a trigger's `ScheduledFuture` only gives implementation-specific delay info at read time, **not a full cron-schedule metadata API**. To display schedules by timezone and rules, store and manage the cron expression, time zone, and latest execution separately.

With `CronTrigger` running against real time, **DST** transitions, system clock changes, restarts, a long-running iteration, or nonexistent hours in a timezone can alter actual firing times. Never assume “cron at 02:30” is guaranteed to occur once every calendar day in every timezone.

## 15. @Scheduled and Programmatic TaskScheduler Differ

Spring has two similar models that differ in handle management:

| Usage | Who Registers the Schedule? | Where Does the Handle Go? | When Appropriate? |
|---|---|---|---|
| `taskScheduler.schedule(...)` in a service | Application code | Returned directly as `ScheduledFuture<?>` | Need to enable/disable/replace schedules by job ID at runtime |
| `@Scheduled(fixedDelay=...)` on a Spring method | Annotation scheduling infrastructure | Method invocation does not return a `ScheduledFuture` directly | Static configuration-driven schedules managed by container |
| `ScheduledTaskRegistrar`/`ScheduledTask` | Spring scheduling registration API | Separate `ScheduledTask` handle with `cancel(...)` | Managing tasks registered via registrar |

Annotation example:

```java
import org.springframework.scheduling.annotation.Scheduled;

@Scheduled(fixedDelay = 60000)
public void cleanCache() {
    // Spring auto-registers and schedules based on annotation.
}
```

This is a **Spring method snippet**, requiring a valid bean and `@EnableScheduling` or equivalent for the annotation to be processed. Normal calls to `cleanCache()` **do not return a `ScheduledFuture`**. If you need per-user cancellation without shutting down the whole bean, consider moving scheduling into a service using programmatic `TaskScheduler`.

Do not fabricate or assume a `ScheduledFuture` from `@Scheduled` if your code never registered/captured a handle; and do not shut down the application-wide scheduler just to turn off one specific schedule.

## 16. Periodic Task Exceptions: Differences Between Spring and Standard Java

This is a key point when using `ScheduledFuture` for **error tracking**.

### 16.1. Raw Java ScheduledExecutorService

With `ScheduledThreadPoolExecutor.scheduleAtFixedRate(...)` and `scheduleWithFixedDelay(...)`, if one execution throws an uncaught exception, Java treats it as **abnormal termination of the periodic series**. Subsequent runs are suppressed; `isDone()` can turn `true` and `get()` throws `ExecutionException` wrapping the cause.

### 16.2. Default Spring ThreadPoolTaskScheduler

Spring typically wraps the `Runnable` in an error-handling wrapper. `TaskUtils.getDefaultErrorHandler(isRepeatingTask)` returns different policies:

- **Repeating tasks:** logs and **suppresses** exceptions by default so the schedule can continue.
- **One-shot tasks:** logs and **propagates** exceptions by default because callers can observe errors via the Future.

Consequently, even when a `@Scheduled` or programmatic periodic run errors out, `ScheduledFuture.isDone()` can still be `false` and the schedule keeps firing. **Do not rely on `isDone()` to count failures**; record the outcome of each individual run instead.

### 16.3. Configuring ErrorHandler When a Different Policy Is Needed

`ThreadPoolTaskScheduler` provides:

```java
scheduler.setErrorHandler(error -> {
    logScheduledFailure(error);
});
```

This is a **configuration snippet** with `logScheduledFailure` defined by the application. If the handler only logs and does not rethrow, it **suppresses errors**. If you want to terminate the schedule after an exception, configure a propagating policy and understand how that affects the Future and periodic series.

Spring offers `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` to log and rethrow, yet using it must be a **deliberate business decision**. A global propagating handler can kill many schedules that ought to recover after transient failures.

Do not confuse `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` (for `@Async void`) with `ThreadPoolTaskScheduler.setErrorHandler(...)` (for the scheduler). They are two separate error-handling paths.

## 17. Cancelling Schedules and Evicting Tasks From the Queue

In `ThreadPoolTaskScheduler` backed by `ScheduledThreadPoolExecutor`, a cancelled task whose due time has not arrived may stay in the queue until its trigger time, depending on the **remove-on-cancel policy**.

Configuration:

```java
ThreadPoolTaskScheduler scheduler =
        new ThreadPoolTaskScheduler();

scheduler.setPoolSize(2);
scheduler.setRemoveOnCancelPolicy(true);
```

This is a configuration snippet before Spring initializes the bean. `setRemoveOnCancelPolicy(true)` instructs the underlying `ScheduledThreadPoolExecutor` to remove cancelled tasks from the queue early whenever possible. This helps if the application frequently creates and cancels thousands of future schedules.

However:

- It **does not cancel all schedules**; your code calling `handle.cancel(...)` selects which schedule to cancel.
- It **does not interrupt running tasks**; `cancel(true)` and task cooperation control interruption requests.
- It **does not bound queue capacity** like `ThreadPoolTaskExecutor`'s `queueCapacity`.
- It **does not replace cleaning up the map/registry** of handles stored by the application.
- When using a different `TaskScheduler` implementation, verify its corresponding policy API; do not assume this setter exists on the `TaskScheduler` interface.

For multi-tenant systems, monitor `queue depth`, active/cancelled schedule counts, and retained heap. Do not treat an unbounded delay queue as a mechanism to survive restarts.

## 18. Shutdown: Cancelling Individual Schedules vs. Closing the Scheduler

`future.cancel(...)` targets **one specific handle**. By contrast, `scheduler.shutdown()` at the executor/scheduler layer affects the pool's entire task set and its policy for accepting new schedules.

In Spring, a `ThreadPoolTaskScheduler` declared as a `@Bean` is managed by `ApplicationContext`. A business service **should not call `shutdown()` on the shared bean** when it only wants to stop one of its own jobs. Doing so can cause other services to hit `TaskRejectedException` when trying to schedule.

Policies to pay attention to:

- `setContinueExistingPeriodicTasksAfterShutdownPolicy(...)`: whether existing periodic tasks continue after shutdown.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(...)`: whether already-scheduled one-shots not yet due execute after shutdown.
- `setWaitForTasksToCompleteOnShutdown(...)` and Spring lifecycle settings: how shutdown waits (or does not wait) when closing the context.

In Spring `ThreadPoolTaskScheduler` 6.2.7, `continueExistingPeriodicTasksAfterShutdown` defaults to `false`; `executeExistingDelayedTasksAfterShutdown` defaults to `true` on `ScheduledThreadPoolExecutor`. Applications requiring **no tasks to run once shutdown starts** must configure explicit policies, verify versions, and test real behavior.

Test shutting down the app with: pending one-shots, an active periodic run, a waiting periodic schedule, interrupted tasks, and schedules being updated concurrently. For jobs that must not be lost across restarts, use persistence/brokers or a distributed scheduler rather than keeping `ScheduledFuture` only on the heap.

## 19. Monitoring Schedules: Handle Status Is Not Enough

A good dashboard separates **schedule registration**, **runs**, **cancellation**, **errors**, and **lifecycle termination**.

| Metric / Field | Meaning | Possible Source |
|---|---|---|
| `schedule.registered` | Schedule registered successfully | Handle-managing service |
| `schedule.cancel.requested` | Cancellation was requested | Control command |
| `schedule.cancel.accepted` | `cancel(...)` returned `true` | Future result |
| `schedule.active` | Schedule remains active in business terms | Registry + Future state |
| `run.started` | An iteration started | Wrapper around Runnable |
| `run.succeeded` | An iteration completed successfully | Wrapper / business logic |
| `run.failed` | An iteration threw an exception | Wrapper / ErrorHandler |
| `run.duration` | Execution duration of one iteration | Per-run timer |
| `run.lastSucceededAt` | Timestamp of latest successful completion | State store |
| `schedule.nextDue` | Planned next trigger time | Application-managed trigger/metadata |

`isDone()`/`isCancelled()` return a snapshot of Future state, and do not provide `lastSucceededAt`, run counts, or errors. `getDelay(...)` can hint at the next wait interval, yet is not a reliable way to compute per-job SLOs or SLAs.

An illustrative wrapper counting runs:

```java
AtomicInteger successCount = new AtomicInteger();

Runnable monitored = () -> {
    long startNs = System.nanoTime();
    try {
        executeBusinessStep();
        successCount.incrementAndGet();
    } finally {
        long elapsedNs = System.nanoTime() - startNs;
        recordDuration(elapsedNs);
    }
};
```

This is a snippet with application-defined `executeBusinessStep`/`recordDuration`. To count errors, add an appropriate `catch` and decide whether to rethrow or suppress according to the schedule's error policy. If the job has side effects, “throwing no exception” does not necessarily prove final success on an external service.

## 20. Managing Cron Across Restarts or Multiple Instances

`ScheduledFuture` is a JVM-local handle, not a distributed coordination mechanism. If an application runs on three pods and all three call `scheduleAtFixedRate(...)` at startup, there will normally be **three independent schedules** and the task can run three times.

Cancelling the Future on pod A does not cancel Futures on pods B or C. Nor is a job guaranteed to survive:

- JVM crash or `kill -9`.
- Pod replacement / rolling deployment.
- Full Spring `ApplicationContext` recreation.
- Changes in job ownership within the cluster.

If work must be guaranteed and executed once per business contract, consider **leader election, distributed locks/leases, a durable job store, an outbox, or a dedicated scheduler**. Whichever option you choose, you still need idempotency and retry/reconciliation policies.

If users have a “Disable schedule” button, a multi-instance system must route the command to the true owner or update state in a distributed store that owners obey. `cancel(false)` in a single process is not a cluster-wide cancellation API.

## 21. Common Mistakes When Using ScheduledFuture

| Mistake | Why Is It Wrong? | Right Approach |
|---|---|---|
| Scheduling and discarding the returned Future | No convenient handle left to cancel that schedule alone | Store handle by job ID if control is required |
| Calling `get()` on a periodic Future to wait for one run | Can wait forever while the schedule series stays active | Use latches/counters/per-run status |
| Treating `isDone()` as “latest run succeeded” | Recurring schedule Future covers the whole series | Measure each run separately |
| Treating `isCancelled()` as “worker stopped” | `cancel(false)` does not interrupt an in-flight run | Wait for task-exit milestone if graceful stop is needed |
| Calling `cancel(true)` believing data rolled back | Interruption is cooperative; side effects do not auto-undo | Timeouts, interrupted checks, idempotency |
| Not checking `null` from `schedule(task, trigger)` | Trigger may produce no next execution | Handle nullability before storing/cancelling |
| Re-registering the same job ID without cancelling the old one | Multiple handles trigger concurrently | Manage registry and replacement policy |
| Only increasing `poolSize` when schedules lag | May be caused by blocking tasks or external bottlenecks | Measure run duration, queue wait, downstream latency |
| Using scheduler for long blocking I/O | Ties up scheduler threads, delaying other jobs | Bound/offload heavy work to a suitable executor |
| Not understanding Spring `ErrorHandler` | Periodic errors may be suppressed while schedule keeps firing | Configure and monitor per-run errors |
| Calling `scheduler.shutdown()` to stop one report | Breaks other schedules sharing the pool | Call `handle.cancel(...)` |
| Not cleaning up finished one-shot handles | Map retains references and leaks memory | Clean up registry per lifecycle |
| Thinking `removeOnCancelPolicy` is `queueCapacity` | It only changes eviction policy for cancelled tasks | Manage load/workers/retained heap separately |
| Writing `@Scheduled` and calling the method expecting a Future | Annotation registration does not return a Future to callers | Choose programmatic `TaskScheduler` when handles are needed |
| Storing `ScheduledFuture` in a database | It is a JVM object, not a durable ID | Store job metadata/status/cron, recreate handles on restart |

## 22. Repeatable Testing for Scheduled Cancellation

Concurrency tests relying on `Thread.sleep(100)` to guess state easily flake in CI. Use `CountDownLatch` / `Future.get(timeout)` to prove concrete milestones.

Minimum test scenarios:

1. **Pending one-shot:** schedule far in the future, cancel before execution; assert `isCancelled`/`isDone` and zero side effects.
2. **Completed one-shot:** schedule immediately, call `get(timeout)`; expect `get()` returns `null` for `Runnable` and side effects occurred.
3. **Periodic after one run:** latch signals first run, call `cancel(false)`, verify no further runs in a reasonable test window; do not rely solely on sleep as proof.
4. **In-flight periodic run:** hold task on a latch, call `cancel(false)`; release latch and observe worker exit. Demonstrate the Future can already be cancelled before task logic exits.
5. **Cancellation with interrupt:** task blocks on an interruptible API, call `cancel(true)`; verify the task receives interruption and runs cleanup. Set a timeout so tests never hang.
6. **Trigger with no runs:** build a Trigger returning `null`, verify `schedule(...)` can return `null`.
7. **Periodic errors:** test both Spring's default suppress policy and a propagating handler if business rules require stopping.
8. **Re-registering the same job ID:** verify no unintended duplicate schedules arise when two callers update concurrently.
9. **Shutdown:** verify accepted and pending tasks follow the configured shutdown policies.
10. **Multi-node:** test your coordination contract separately if clustered; never assume Futures are shared.

A test can use a single-worker scheduler with latches to enforce deterministic ordering; however, never make a task inside a single-worker scheduler wait on another Future submitted to the same scheduler, as that can cause starvation deadlock.

### 22.1. Illustrative Test for Cancellation While Task Is Running

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);
CountDownLatch exited = new CountDownLatch(1);

ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(() -> {
    started.countDown();
    try {
        release.await();
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    } finally {
        exited.countDown();
    }
}, Duration.ofHours(1));

if (!started.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("First run not observed");
}

boolean cancelled = handle.cancel(false);
// Here handle may already be cancelled, while the task still waits on release.
release.countDown();

if (!exited.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Task has not exited");
}
```

This is an **integration test snippet** with an initialized `scheduler`; the test method must handle `InterruptedException` and import concurrent classes. The `exited` latch separates “the Future was cancelled” from “the Runnable body actually exited”. Use `try/finally` in real tests to always release `release` even if assertions fail.

## 23. Practice Exercises

### Exercise 1 — Distinguishing One Run From the Whole Schedule

A `ScheduledFuture` from `scheduleAtFixedRate(...)` has completed 20 successful runs. `isDone()` is still `false`. Is this a bug?

**Suggested answer:** No. The handle represents the periodic series, which has not ended; successful run counts must be tracked separately.

### Exercise 2 — Cancelling Without Interrupt

A job is sending a file; the caller calls `cancel(false)` and gets `true`. Can the file resource held by the worker be deleted immediately?

**Suggested answer:** Not necessarily. The active run may still be continuing; you need full stop coordination, cleanup, and resource ownership rules.

### Exercise 3 — Cancelling Before Due Time

Schedule a one-shot one hour ahead. Cancel immediately with `cancel(false)`. What should `isDone` and `isCancelled` return? How does `get()` behave?

**Suggested answer:** For a successfully cancelled Future, both are `true`; `get()` throws `CancellationException` instead of returning a result.

### Exercise 4 — Spring vs. Raw Java

Why does a periodic task throwing an exception still execute subsequent runs in `ThreadPoolTaskScheduler`, even though raw Java `ScheduledThreadPoolExecutor` stops the series?

**Suggested answer:** Spring uses an error-handling wrapper; by default for repeating tasks it logs and suppresses exceptions. Look up `ThreadPoolTaskScheduler.setErrorHandler(...)` and `TaskUtils`.

### Exercise 5 — `@Scheduled` vs. `TaskScheduler`

You want each user to turn off their own report schedule without stopping other users' schedules. Choose static `@Scheduled` or the programmatic `TaskScheduler` API?

**Suggested answer:** Programmatic `TaskScheduler` is more convenient when handles must be stored and cancelled by job ID, though concurrency and cluster ownership still need to be solved.

### Exercise 6 — Nullable Cron Trigger

A custom Trigger yields no next execution time. `scheduler.schedule(work, trigger)` returns `null`. Should you insert null into the registry and call `cancel(false)`?

**Suggested answer:** No. Handle the “no schedule” case right at registration and return an appropriate status to the caller.

### Exercise 7 — Designing Graceful Shutdown

A job is in a long execution run when a user clicks “Stop”. Design a two-phase flow so you do not report “fully stopped” while the worker is still active.

**Suggested answer:** Cancel the handle to stop future runs; track the active run and wait/observe the current run exiting, with a timeout and explicit interrupt/compensation policies.

### Exercise 8 — Running the Java 17 and Spring Demos

Run `ScheduledFutureCancelDemo.java` and `ScheduledHandleDemo.java`. Explain why both can cancel a future schedule, while the Spring example also handles a periodic schedule after its first run.

**Suggested answer:** Both use the `ScheduledFuture` contract; the Spring example obtains handles from `TaskScheduler` and uses a latch to mark the first periodic run before cancelling.

### Exercise 9 — Multiple Pods

Three pods each schedule the same job. One pod cancels its local Future and responds “all cancelled”. Is that conclusion accurate?

**Suggested answer:** No. Each pod has a separate scheduler and Future. Distributed coordination, durable state, and idempotency are required.

## 24. Pre-Deployment Review Checklist

When a PR adds a dynamic cancellable schedule, verify:

1. Every schedule has an **owner** and a place storing `ScheduledFuture<?>` by local job ID.
2. The right `TaskScheduler` overload is chosen: one-shot, fixed rate, fixed delay, or Trigger.
3. `schedule(Runnable, Trigger)` handles the `null` return case.
4. `cancel(false)`/`cancel(true)` is chosen based on interruptibility and task side effects.
5. Code never claims “worker stopped” solely because `isCancelled` is `true`.
6. Code never calls `get()` on a periodic Future to wait for a single run.
7. `isDone` is understood as the terminal state of **the entire Future**, not the last run's outcome.
8. Per-run execution/failure stats are recorded if business monitoring needs them.
9. Spring's `ErrorHandler` is explicitly defined; not confused with raw Java executor error semantics.
10. `setRemoveOnCancelPolicy` is considered if many long-delayed schedules are cancelled.
11. The scheduler's thread pool and shutdown policies are tested against requirements.
12. The shared scheduler bean is never shut down just to stop one handle.
13. The registry handles concurrency/replace/cancel, cleans up finished handles, and avoids reference leaks.
14. Tasks do not block scheduler threads too long; timeouts/downstream bulkheads are present if needed.
15. In a cluster, owner/leader/lease/idempotency mechanisms exist if duplicate runs must be prevented.
16. Critical schedules persist metadata in durable storage if they must survive restarts.
17. Tests use latches and Futures with timeouts, independent of `Thread.sleep` and log ordering.

## 25. Summary

- **`ScheduledFuture<?>` is the handle of a schedule created via `TaskScheduler`**, used to inspect status and request cancellation without stopping the entire scheduler.
- **`isDone()` is the Future's terminal state, not “latest periodic run succeeded”.** `isCancelled()` only reflects the Future's cancellation state.
- **`cancel(false)` prevents future runs without requesting to interrupt an in-flight run; `cancel(true)` only attempts interruption**, without guaranteeing a hard stop or rollback.
- **`getDelay(...)` estimates remaining delay until due**, not an absolute timestamp, history, or SLO.
- **`get()` is useful for one-shots**, yet can wait indefinitely on a live periodic series; track individual runs with separate state/callbacks.
- **`schedule(task, Trigger)` can return `null`**; handle it before storing or cancelling.
- **Spring has a different error policy from raw Java for repeating schedules**: exceptions may be logged/suppressed so the schedule continues, so monitor per-run errors.
- **Store handles by job ID and manage lifecycle**, distinguishing single-job cancellation from shared-scheduler shutdown; in clusters, durable coordination is required.

### Official References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework Javadoc — TaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework 6.2.7 Javadoc — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework Javadoc — TaskUtils and ErrorHandler](https://docs.spring.io/spring-framework/docs/6.0.1/javadoc-api/org/springframework/scheduling/support/TaskUtils.html)
- [Java SE 17 Javadoc — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)
- [Java SE 17 Javadoc — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 Javadoc — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java SE 17 Javadoc — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
