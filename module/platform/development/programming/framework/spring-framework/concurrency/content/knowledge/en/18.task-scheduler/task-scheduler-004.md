# scheduleWithFixedDelay() and the Pause After Completion

## 1. Goal and Real-World Scenario

A Spring application periodically synchronizes inventory from a partner. One processing run may take 2 seconds, while another takes 15 seconds. The business requirement is: **after a run actually finishes, pause for 5 more seconds before starting the next run**. If the partner is slow, we do not want to queue up a burst of new runs chasing an old schedule.

That is the meaning of `TaskScheduler.scheduleWithFixedDelay(...)` in Spring Framework: the `delay` duration is measured **from when the previous execution finishes until when the next execution is eligible to start**. It is not the period between two start times, not a sleep inside the task itself, and not a mechanism that spawns unbounded background threads.

~~~text
fixed delay = 5 seconds

Run 1:   START 10:00:00 ---- process 7 s ---- END 10:00:07
                                                     |
                                                     +-- pause at least 5 s
Run 2:                                      START 10:00:12 ---- process 2 s ---- END 10:00:14
                                                                                         |
                                                                                         +-- pause at least 5 s
Run 3:                                                                          START 10:00:19 ...

Formula: start(n+1) >= finish(n) + delay
Actual timing also depends on scheduler resources, OS latency, and load.
~~~

Do not read `delay=5s` as “once every 5 seconds”. When run 1 takes 7 seconds, **the interval between the two starts is at least 12 seconds**, not 5 seconds. If run 2 takes 2 seconds, the start-to-start interval from run 2 to run 3 is at least 7 seconds.

Objectives after this lesson:

1. Use the two overloads `scheduleWithFixedDelay(Runnable, Duration)` and `scheduleWithFixedDelay(Runnable, Instant, Duration)` properly.
2. Distinguish **fixed delay**, **fixed rate**, **cron**, `initialDelay`, and one-shot schedules.
3. Understand why a **single fixed-delay series does not overlap itself**, while other jobs, duplicate annotations, and multiple pods can still run concurrently.
4. Know how to control `ScheduledFuture`, cancellation, business errors, timeouts, shutdown, pool size, and observability.
5. Write a Java 17 program and a Spring Boot application demonstrating completion followed by the pause.

Illustrated versions: **Java 17, Spring Framework 6.x, Spring Boot 3.3.5**, using platform threads and standard `ThreadPoolTaskScheduler`. Specific details for Java 21 virtual threads are noted separately.

## 2. The TaskScheduler API in Spring Framework

`org.springframework.scheduling.TaskScheduler` is Spring's scheduling abstraction. It decouples business code from creating and managing a `ScheduledExecutorService`/worker threads. Key methods:

~~~java
// Abbreviated signatures of TaskScheduler in Spring Framework 6.x:
ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> schedule(
        Runnable task, Instant startTime);
~~~

This is an **API signature excerpt**, not a standalone Java class. The `task` parameter is `Runnable`; `Duration` comes from `java.time`, `Instant` is an absolute timestamp; `ScheduledFuture<?>` comes from `java.util.concurrent`.

### 2.1. Starting as Soon as Possible

~~~java
// Snippet in a service with an injected TaskScheduler.
ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        () -> refreshInventory(),
        Duration.ofSeconds(5));
~~~

- The first run **is eligible to run as soon as possible** when the scheduler has a worker, without mandating a 5-second wait.
- Only after `refreshInventory()` finishes does the scheduler count the 5-second pause until the next run.
- If the scheduler is overloaded, has no free worker, or is paused, the actual time may be later.
- `handle` lets you cancel the repeating series; it **does not hold the result of each run**.

`refreshInventory` and `scheduler` in the snippet are assumed application components. Even without `@EnableScheduling`, you can call the `TaskScheduler` API directly as long as an initialized / Spring-managed scheduler exists.

### 2.2. Specifying the Time of the First Run

~~~java
// Snippet in a service that already has a TaskScheduler.
Instant firstRun = scheduler.getClock().instant()
        .plus(Duration.ofSeconds(10));

ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        () -> refreshInventory(),
        firstRun,
        Duration.ofSeconds(5));
~~~

The second overload uses `startTime` for the **first execution**, and thereafter still waits 5 seconds **from when each run finishes**. If `startTime` is already in the past, the task is eligible to run as soon as possible. `scheduler.getClock()` keeps the scheduler's time source consistent; in simple examples `Instant.now()` also works if the system clock matches.

**Do not confuse** `startTime` with a pause after each run. If you want “wait 10 seconds before the first run, then 5 seconds after each completion”, this is the direct way.

### 2.3. Why Use Duration Instead of long?

Overloads taking `long` in milliseconds used to exist, but were deprecated starting in Spring Framework 6.0 in favor of `Duration`. Writing `Duration.ofSeconds(5)` prevents confusing `5000` milliseconds with seconds. In applications with configuration properties, parse them explicitly into `Duration` to validate and avoid ambiguous units.

## 3. Fixed Delay vs. Fixed Rate and Cron

| Mechanism | Next Calculation Mark | Suitable When |
| --- | --- | --- |
| `scheduleWithFixedDelay(task, delay)` | **Completion** of run n + delay | Polling APIs/DBs, periodic sync, wanting a rest after processing |
| `scheduleAtFixedRate(task, period)` | **Planned start** of run n + period | Sampling/heartbeats at a roughly fixed cadence |
| `schedule(task, instant)` | A single specified timestamp | Run once, no repetition |
| `@Scheduled(cron = "...")` | Explicit wall-clock marks (time/date, timezone) | Daily reports, time-of-day jobs |
| `@Scheduled(fixedDelay = ...)` | Completion of previous invocation + delay | Same fixed-delay semantics via annotation |

Example with `period/delay=5s`, first run taking 8s:

~~~text
FIXED DELAY:
  start 00:00 -> end 00:08 -> pause 5s -> start ~00:13 -> ...

FIXED RATE on ScheduledThreadPoolExecutor:
  planned starts: 00:00, 00:05, 00:10, 00:15...
  first run takes 8s; the next due run may execute immediately once the first finishes.
  Successive invocations OF THE SAME periodic task do not overlap themselves
  in ScheduledThreadPoolExecutor, though back-to-back runs may occur.

CRON:
  e.g., 02:00 daily is a wall-clock mark; affected by timezone/DST.
~~~

**Fixed rate does not automatically mean “run one task in parallel across multiple workers”.** With JDK `ScheduledThreadPoolExecutor`, consecutive runs of **the same periodic task** do not overlap, even when the pool has multiple workers; however, if a run exceeds the period, there may be no pause after completion. **Different** scheduled tasks may compete or run concurrently depending on worker count.

**Fixed delay does not make up for missed schedules.** When a run takes 30 minutes, the scheduler does not spawn 360 runs to catch up on elapsed 5-second intervals. It waits for the current run to finish and then counts the delay before the next run. This property helps polling avoid piling up load, though it is unsuitable if the business must process **every historical time slot**. That scenario needs a job ledger / data cursor or a business scheduler with catch-up support.

### 3.1. Fixed Delay Is Not Debounce/Throttle

- **Debounce:** after each new event, typically pushes back the execution time, or only executes once no events arrive for an interval.
- **Throttle / rate limit:** caps the number of executions/requests within a window, potentially shared across multiple nodes.
- **Fixed delay:** a periodic task series; only after the current run completes does it count the rest time until the next run.

If a server receives 10,000 events/s, `scheduleWithFixedDelay` does not solve event ingestion or backpressure on its own. It only governs **when** each run of a periodic job starts.

## 4. What Exactly Does “Completion” Mean?

In `TaskScheduler` with a synchronous `Runnable`, “completion” means **`Runnable.run()` has returned or exited via an exception handled under the scheduler's policy**. This does **not automatically** mean the actual business work is finished if `run()` merely dispatches something else.

### 4.1. Pitfall: Runnable Only Submits and Exits

~~~java
// Anti-pattern: snippet; asyncWorker is an application service.
scheduler.scheduleWithFixedDelay(() -> {
    asyncWorker.generateReport(); // Dispatches to another executor and returns very quickly.
}, Duration.ofSeconds(5));
~~~

If `generateReport()` has `@Async` and the caller goes through the Spring proxy, the `Runnable` only **submits the work**. The scheduler's “run completion” is measured when the **submission call** returns, without waiting for the report to finish processing. Therefore multiple reports can still run concurrently even though the scheduler uses fixed delay.

The same happens with:

~~~java
// Snippet: fire-and-forget inside a Runnable.
CompletableFuture.runAsync(() -> generateReport(), otherExecutor);
// Runnable calls runAsync and returns without waiting for completion.
~~~

The solution must follow the **business contract**: if runs must **not overlap** with respect to actual completion, keep the main work synchronous inside the `Runnable`, or manage a workflow with a `RUNNING` state and forbid dispatching a new run until the previous one is terminal. You can `join/get` a Future inside the Runnable to wait, though that **blocks a scheduler worker**; you need timeouts, interruption handling, and must not use the same blocked pool to run the awaited child tasks, or you risk starvation/deadlock.

### 4.2. Fixed Delay Does Not Automatically Guarantee Exactly-Once

If a deployment has 3 Spring pods, each pod can register its own fixed-delay job and run the same logic on each JVM. From a scheduler perspective, **each pod has a non-overlapping series**; cluster-wide there can still be 3 concurrent runs. If a job must run on only one instance, use a distributed lock/lease, DB claiming, a message broker, or a central scheduler, combined with idempotency.

Even within one JVM, two `@Scheduled` annotations on the same method (repeatable annotation), two `TaskScheduler.scheduleWithFixedDelay` calls for the same Runnable, or two contexts/bean instances registering duplicates can create **two independent series**. “Non-overlap” applies only to **one handle of one periodic scheduling registration**, not to every invocation reaching the same method via any path.

## 5. Standalone Java 17 Demo: Proving the Pause After Completion

We use a single fixed worker and `CountDownLatch` to hold **run 1 active**, then measure a minimum gap from when run 1 finishes to when run 2 starts. We do not use `Thread.sleep` as proof and do not rely on arbitrary OS timing.

Save the file **`FixedDelayDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class FixedDelayDemo {
    private static void await(CountDownLatch latch, String name)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out waiting for " + name);
        }
    }

    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        AtomicInteger executions = new AtomicInteger();
        AtomicLong firstFinished = new AtomicLong();
        AtomicLong secondStarted = new AtomicLong();

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStartedSignal = new CountDownLatch(1);

        ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                () -> {
                    int attempt = executions.incrementAndGet();
                    if (attempt == 1) {
                        firstStarted.countDown();
                        try {
                            releaseFirst.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                        } finally {
                            firstFinished.set(System.nanoTime());
                        }
                    } else if (attempt == 2) {
                        secondStarted.set(System.nanoTime());
                        secondStartedSignal.countDown();
                    }
                },
                0, 150, TimeUnit.MILLISECONDS);

        try {
            await(firstStarted, "first start");

            // While run 1 has not finished, run 2 cannot start yet.
            System.out.println("SECOND_DURING_FIRST="
                    + (secondStartedSignal.getCount() == 0));

            releaseFirst.countDown();
            await(secondStartedSignal, "second start");

            System.out.println("SECOND_AFTER_FIRST_END="
                    + (secondStarted.get() > firstFinished.get()));

            long gapNanos = secondStarted.get() - firstFinished.get();
            System.out.println("GAP_AT_LEAST_100_MS="
                    + (gapNanos >= TimeUnit.MILLISECONDS.toNanos(100)));

            System.out.println("TWO_OR_MORE_RUNS="
                    + (executions.get() >= 2));
        } finally {
            releaseFirst.countDown();
            handle.cancel(false);
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not stop");
            }
        }

        System.out.println("CANCELLED=" + handle.isCancelled());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 FixedDelayDemo.java
java FixedDelayDemo
~~~

Output lines printed by the application:

~~~text
SECOND_DURING_FIRST=false
SECOND_AFTER_FIRST_END=true
GAP_AT_LEAST_100_MS=true
TWO_OR_MORE_RUNS=true
CANCELLED=true
~~~

**Why is the result deterministic?**

- `firstStarted` confirms the scheduler entered run 1 before checking; `releaseFirst` is still closed so run 1 has not finished. A recurring fixed-delay task cannot start run 2 while run 1 is still processing.
- `firstFinished` is recorded right before `run()` returns. The scheduler starts counting the 150 ms delay **after** the task actually ends, so `gapNanos` measures at least the delay; the assertion uses a conservative 100 ms threshold to avoid claiming exact millisecond-level measurement.
- `secondStartedSignal` marks that run 2 entered the method; the `TWO_OR_MORE_RUNS` check does not depend on whether run 3 happened yet.
- `cancel(false)` cancels subsequent triggers of the periodic task. It does not mean “any operations sent to a DB are rolled back”, and `shutdownNow()` only requests interrupting still-running tasks.

The demo uses JDK `ScheduledExecutorService` to illustrate the same underlying principle as `ThreadPoolTaskScheduler`; a runnable Spring version is in the next section. If the JDK suffers severe resource starvation causing latches to time out, the program fails explicitly instead of hanging forever.

## 6. Spring Boot Demo: scheduleWithFixedDelay(Runnable, Duration)

This project uses **Java 17, Maven, Spring Boot 3.3.5**. It registers a `ThreadPoolTaskScheduler` bean, calls `TaskScheduler.scheduleWithFixedDelay`, and demonstrates the pause starting **after run 1**. `ApplicationRunner` intentionally waits with latches to print verification results and then cancels the recurring schedule; no web server, DB, or files beyond those listed are required.

### 6.1. Structure

~~~text
spring-fixed-delay/
├── pom.xml
└── src/main/java/com/example/scheduler/
    └── FixedDelayApplication.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-fixed-delay</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. FixedDelayApplication.java

~~~java
package com.example.scheduler;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
public class FixedDelayApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(FixedDelayApplication.class, args)) {
            // After the runner, close the context and release registered resources.
        }
    }

    @Bean("demoScheduler")
    ThreadPoolTaskScheduler demoScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("fixed-delay-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        return scheduler;
    }

    @Bean
    ApplicationRunner verifyFixedDelay(
            @Qualifier("demoScheduler") TaskScheduler scheduler) {
        return args -> {
            AtomicInteger count = new AtomicInteger();
            AtomicLong finishedFirst = new AtomicLong();
            AtomicLong beganSecond = new AtomicLong();

            CountDownLatch firstBegan = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            CountDownLatch secondBegan = new CountDownLatch(1);

            Runnable task = () -> {
                int n = count.incrementAndGet();
                if (n == 1) {
                    firstBegan.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        finishedFirst.set(System.nanoTime());
                    }
                } else if (n == 2) {
                    beganSecond.set(System.nanoTime());
                    secondBegan.countDown();
                }
            };

            ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                    task, Duration.ofMillis(150));

            try {
                if (!firstBegan.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First run did not start");
                }
                System.out.println("SECOND_WHILE_FIRST_RUNNING="
                        + (secondBegan.getCount() == 0));

                release.countDown();
                if (!secondBegan.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Second run did not start");
                }

                System.out.println("SECOND_AFTER_FIRST_END="
                        + (beganSecond.get() > finishedFirst.get()));
                System.out.println("PAUSE_AT_LEAST_100_MS="
                        + (beganSecond.get() - finishedFirst.get()
                                >= TimeUnit.MILLISECONDS.toNanos(100)));
                System.out.println("RUNS_AT_LEAST_2=" + (count.get() >= 2));
            } finally {
                release.countDown();
                handle.cancel(false);
            }

            System.out.println("HANDLE_CANCELLED=" + handle.isCancelled());
        };
    }
}
~~~

**What the code means:**

- The `ThreadPoolTaskScheduler` bean is initialized, lifecycle-managed, and closed by the container when the context closes. `setPoolSize(1)` is only to keep the demo easy to reproduce and read; production must size according to task count, processing time, and SLOs.
- `@EnableScheduling` is not used because the example calls the **TaskScheduler API directly**. The `@EnableScheduling` annotation is only required for discovering and registering `@Scheduled` methods.
- `ApplicationRunner` retains a `ScheduledFuture<?>` to cancel the schedule after observing two runs. Without cancelling, the periodic task could keep running until scheduler shutdown.
- The `CountDownLatch` instances verify the ordering relationship between the active run and the next run, without relying on `Thread.sleep` or log ordering across multiple workers.
- `Duration.ofMillis(150)` is the pause **after** the previous run finishes, not a period between two invocations.

### 6.4. Running and Results

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Ignoring Boot/Maven logs, the program prints:

~~~text
SECOND_WHILE_FIRST_RUNNING=false
SECOND_AFTER_FIRST_END=true
PAUSE_AT_LEAST_100_MS=true
RUNS_AT_LEAST_2=true
HANDLE_CANCELLED=true
~~~

These lines evaluate behavioral properties; no absolute timestamps are printed because timestamps depend on the environment. If the scheduler environment is slow, an actual pause **longer** than configured still satisfies fixed-delay semantics. The measurement uses a 100 ms threshold for a 150 ms delay, rather than claiming the scheduler is always accurate to the nanosecond.

## 7. Using @Scheduled(fixedDelay) Instead of the Direct API

If you only need to periodically invoke a method known at application startup, `@Scheduled` is more concise. Example in a Spring Boot application with `@EnableScheduling`:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InventoryPoller {
    @Scheduled(
            initialDelay = 2,
            fixedDelay = 5,
            timeUnit = TimeUnit.SECONDS)
    public void poll() {
        // Perform one synchronization pass; return when the run finishes.
        syncInventory();
    }

    private void syncInventory() {
        // Business code must have timeouts/observability.
    }
}
~~~

In a `@Configuration` class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfig {
}
~~~

These are **two illustrative classes that can be placed in the same Spring project**, not part of the direct-API demo in Section 6. With the annotation above:

- The first run is eligible after `initialDelay=2s` from when the task is registered / the scheduler starts per lifecycle; not “2 seconds after the first HTTP request”.
- After `poll()` returns, the scheduler waits `fixedDelay=5s` before the next run. If `poll()` takes 8s, two starts are spaced by at least about 13s.
- `timeUnit = TimeUnit.SECONDS` makes the unit for `2`/`5` explicit. If omitted, `@Scheduled` defaults to milliseconds.
- Standard scheduled methods take no parameters; avoid unbounded blocking, set network/DB timeouts, and record failure states.

You can use `fixedDelayString = "PT5S"` or a Spring-resolved property to configure from the environment. When using external properties, check units, valid values, and active profiles, because a negative/invalid value can fail schedule registration. If you change the delay while the application is running, do not assume the registered annotation automatically reschedules immediately; depending on the case you must re-register or design a dynamic trigger.

### 7.1. Annotation Does Not Mean @Async Proxy Rules

`@Scheduled` is detected and registered by Spring's scheduling infrastructure, whereas `@Async` typically relies on a Spring proxy/interceptor. Do not take `@Async`'s self-invocation rule and claim that `@Scheduled` only runs when a request passes through a proxy. The scheduler **invokes the method directly** on the registered schedule. Conversely, declaring `@Scheduled` without enabling scheduling infrastructure in the context means the method may never be registered.

If a method carries both `@Scheduled` and `@Async`, or a scheduled method calls another async bean, verify what counts as “finished”. Returning immediately after dispatch can make fixed delay apply only to **submitting the task** rather than waiting for the business task to finish.

### 7.2. Do Not Confuse the Scheduler Bean and Executor Bean

`spring.task.execution.*` configures Spring Boot's async task execution when auto-configuration applies; `spring.task.scheduling.*` is for the scheduler. A `ThreadPoolTaskExecutor` for `@Async` does not automatically become the `TaskScheduler` for `@Scheduled`. When defining both layers, name beans clearly and configure the right type.

Example of Spring Boot properties when auto-configuring the scheduler in an eligible environment:

~~~properties
# Illustrative override provided by the application; NOT the default:
spring.task.scheduling.pool.size=3
spring.task.scheduling.thread-name-prefix=poll-
~~~

If the application already creates a `@Bean ThreadPoolTaskScheduler` via setters as in Section 6, do **not** expect Boot properties to necessarily override the pool size set in code. Inspect the actual bean and resolved configuration.

## 8. Is It Really Non-Overlapping?

### 8.1. Within the Same Periodic Registration

For standard `ThreadPoolTaskScheduler`, the backend is JDK `ScheduledExecutorService/ScheduledThreadPoolExecutor`. Triggers of **one** task registered via `scheduleWithFixedDelay` do not overlap: the next run only becomes eligible after the previous run finishes and the delay elapses. Increasing `poolSize` to 10 does not turn that single schedule into 10 parallel invocations.

### 8.2. Across Different Scheduled Jobs

Two jobs `refreshProductCatalog` and `refreshSupplierCatalog` can run concurrently if the scheduler has multiple workers, because they are **two separate registrations**. If `poolSize=1`, one long job delays the other even though each has its own delay. Thus fixed delay is a timing rule *per schedule*, not a mutex locking the entire scheduler.

### 8.3. When Code Offloads Work to an Async Executor

If `Runnable.run()` just submits a Future to another executor and returns, the scheduled call can finish in a few milliseconds. The business task may still be running when the next dispatch arrives; fixed delay does not automatically prevent overlap of **child Futures**.

### 8.4. Across Application Instances

Each pod/JVM has an independent scheduler. When running multiple pods, each pod can start its own job and contend on DB updates. If only one job may run cluster-wide, use a distributed lock/lease, atomic DB claim, or a message broker. Idempotency is needed to handle restarts/retries, rather than relying solely on cron/fixed delay and pool size.

### 8.5. With Virtual Threads and SimpleAsyncTaskScheduler

Spring Framework 6.1+ includes `SimpleAsyncTaskScheduler` tailored for virtual threads. Notably, fixed-delay tasks in this implementation run on **a single scheduler thread**, rather than offloading each run to a new thread like fixed rate/cron. Spring documentation recommends considering **fixed rate or cron** with a virtual-thread-aligned scheduler, especially when work can block. Do not mechanically carry assumptions about `ThreadPoolTaskScheduler` over to another implementation merely because both share the `TaskScheduler` interface.

## 9. Exceptions: Distinguishing Raw JDK Scheduler From Spring Wrapper

This is one of the most important diagnostic pitfalls.

### 9.1. Raw Java ScheduledThreadPoolExecutor

Per JDK `ScheduledExecutorService.scheduleWithFixedDelay`, if any execution of the periodic command throws an unhandled unchecked exception, **subsequent executions are suppressed**. The series's `ScheduledFuture` can transition to exceptional completion; calling `get()` throws `ExecutionException`. While a healthy series is still running, `ScheduledFuture.get()` **does not return a result per run**, because a periodic task by nature has not terminated.

~~~java
// JDK snippet, assuming rawExecutor is a ScheduledExecutorService.
ScheduledFuture<?> handle = rawExecutor.scheduleWithFixedDelay(
        () -> {
            throw new IllegalStateException("failed");
        },
        0, 5, TimeUnit.SECONDS);

// After the first run fails, get() may throw ExecutionException
// and the schedule does not automatically restart.
~~~

### 9.2. Standard Spring ThreadPoolTaskScheduler

Spring `ThreadPoolTaskScheduler` decorates repeating `Runnable`s with Spring's error handling. With the default error handler for **repeating tasks**, Spring typically **logs and suppresses the exception**, allowing subsequent runs to continue. Therefore you must not transfer raw JDK's “one exception stops the schedule” rule to every Spring application verbatim.

Spring `TaskUtils` provides two illustrative strategies:

- `LOG_AND_SUPPRESS_ERROR_HANDLER`: logs the error, does not rethrow; periodic runs can continue.
- `LOG_AND_PROPAGATE_ERROR_HANDLER`: logs the error and rethrows; that generally prevents subsequent runs on a JDK scheduler.

If the application supplies `setErrorHandler(...)`, the outcome depends on whether the handler rethrows or not.

~~~java
// Snippet in @Configuration: proactively log + continue.
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
scheduler.setErrorHandler(error -> {
    log.error("Scheduled iteration failed", error);
    failedRunsCounter.increment();
    // Do not throw: failed iteration is recorded, schedule continues.
});
~~~

`log` and `failedRunsCounter` are assumed business components; the snippet is not a standalone program. If an error means the job must stop, choose an explicit stop policy and record status in a job store; do not rely on a single log line.

A task “finishing because the wrapper handled the exception” still causes the scheduler to count the next delay; **schedule run completion does not mean business success**. Track `FAILED`/`SUCCEEDED` run counts separately.

### 9.3. Using Future Properly

- `scheduleWithFixedDelay` returns `ScheduledFuture<?>` to **cancel/check status**, not to call `get()` for each run's result.
- `handle.get()` while a healthy schedule is running can wait indefinitely; avoid calling it immediately on an HTTP/startup thread to “wait for the first run to finish”.
- To track the first run, use callbacks/metrics/job state, latches in tests, or an application-managed result Future with a deadline.
- `handle.isDone()` may simply indicate the schedule was cancelled/terminated, **not** that “the latest run succeeded”.
- When task submission is rejected due to scheduler shutdown/overload, Spring can throw `TaskRejectedException` **immediately on calling schedule**, before returning a handle.

## 10. Cancellation, Application Shutdown, and ScheduledFuture

### 10.1. Cancelling a Repeating Schedule

~~~java
ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        this::runCleanup, Duration.ofMinutes(2));

// In the place managing the job's lifecycle:
boolean cancelled = handle.cancel(false);
~~~

`cancel(false)` blocks future runs of the series. If a task is currently running, cancellation does not necessarily halt in-progress processing immediately. `cancel(true)` allows requesting an interrupt on supporting backends, **without guaranteeing** DB transaction rollback, vanishing partially written files, or immediate stopping of uninterruptible I/O.

Retain `ScheduledFuture<?>` per job registration; do not create a new schedule per HTTP request and discard the handle, because having no place to cancel/monitor can leave many periodic jobs running concurrently.

### 10.2. Shutdown and Spring Lifecycle

`ThreadPoolTaskScheduler` is a Spring-managed bean with initialization/shutdown lifecycle. When the context closes, the application must stop/cancel schedules according to the chosen policy. Spring 6.1+ adds pause/resume and graceful-shutdown controls; specifics depend on version/configuration. For jobs with critical side effects, check policies for running tasks, queued tasks, shutdown timeouts, and how data consistency is ensured after restart.

A `ScheduledFuture<?>` is not a durable job queue. If a pod crashes, every in-JVM handle is lost; to know how far processing got last time, persist a checkpoint/watermark in the DB rather than relying on `isDone()`.

### 10.3. Note on Registration Timing

A service can register its schedule in `@PostConstruct`, though during bean initialization dependencies/proxies may not be finalized or an explicit stop lifecycle may be needed. Depending on requirements, use bean configuration, `ApplicationRunner`, `SmartLifecycle`, post-refresh events, or `@Scheduled` appropriately; avoid double registration on context refresh or when multiple instances are created.

## 11. Designing Production Polling Jobs: Pause, Timeouts, Errors, and Data

Consider a job fetching new invoices from a partner API by cursor. The requirement “pause 5s after the previous run finishes” suits fixed delay, yet safe operation requires adding:

1. **True start/completion points:** log `startedAt`, `finishedAt`, and `outcome` (success/failure) inside the `Runnable` or the job-managing transaction. Do not mark complete upon merely dispatching another Future.
2. **I/O timeouts:** connection/read timeouts for HTTP clients, query/transaction timeouts for DBs. If the `Runnable` hangs forever, the next run will never be scheduled despite a 5s delay setting.
3. **Checkpoints:** update the cursor/watermark only after data is durably persisted, preventing skipped records across restarts or retries.
4. **Idempotency:** if requests or jobs are retried or multiple pods run concurrently, deduplicate by natural key / unique index / conditional upsert.
5. **Backpressure:** bound batch sizes, concurrent requests to the partner, DB throughput, and timeouts; fixed delay only spaces **between runs**, it does not cap resources **inside a run**.
6. **Errors and retries:** distinguish transient errors (429/503, timeouts) from business errors (invalid payload, authorization). Exponential backoff/jitter and circuit-breaker policies may be used. If error-dependent dynamic intervals are needed, an immutable fixed delay may not suffice.
7. **Shutdown:** persist state and cancel the schedule; let in-flight runs finish safely or allow restarts to recover via a job ledger.
8. **Monitoring:** metrics for `successful_runs`, `failed_runs`, `last_success_timestamp`, `last_run_duration`, `delay_from_finish_to_next_start`, `scheduler_queue_delay`, and rejected scheduling attempts.
9. **Clustering:** if only one worker cluster-wide may run, use a distributed lease / off-JVM scheduler; do not treat `poolSize=1` on each pod as a distributed lock.

If exact local wall-clock timing is required (e.g., 08:00 daily), fixed delay is unsuitable because it **drifts** with processing time plus pause. In that case use cron with an explicit timezone and dedicated DST/missed-execution rules. If a partner mandates at most one request every 5 seconds after *returning a response*, fixed delay is a useful approximation, though you must still account for all other callers/tasks hitting that partner.

## 12. Testing Schedulers Without Random Sleeps

A good test suite covers these scenarios:

| Test | Evidence to Observe |
| --- | --- |
| Run 1 held by a latch | Run 2 has not started while run 1 has not finished |
| Run 1 released | Run 2 starts only after the delay has elapsed since completion |
| Run 1 takes longer than delay | No backlog of multiple runs for the same registration |
| Cancelling `ScheduledFuture` | No new runs after cancellation (account for cancellation/race state) |
| Task throws exception | Distinguish Spring default handler continuing vs. raw JDK suppression |
| One long job A + another job B | PoolSize=1 can delay B; multiple workers can run concurrently |
| Executor shutdown | New registrations rejected/cancelled per policy, no infinite wait on Future |
| Same code on two pods | Both can run concurrently; coordination needed if cluster-single is required |
| Task only dispatches `@Async` | Fixed delay measures dispatch completion, not business completion |
| Virtual-thread-aligned scheduler | Fixed-delay semantics must be tested on the actual implementation |

Why shouldn't you write tests like “`Thread.sleep(200)` then assert exactly 2 runs”? Because slow CI, GC pauses, and OS scheduling are non-deterministic. For business logic, extract processing into standalone functions for synchronous unit testing; test scheduling using latches or integration tests with bounded timeouts. Allow timing tolerance rather than requiring exact millisecond precision.

### Testing Overlap and Ordering

An `AtomicInteger active` combined with `maxActive.accumulateAndGet(...)` can prove the same registration had no two concurrent invocations. Yet for single-worker fixed delay in the demo, the latches in Section 5 are clear enough. If the `Runnable` offloads tasks to another executor, the active counter must wrap the **actual business work**, not just the fast dispatch wrapper that returns immediately.

When multiple registrations exist, test independent jobs and shared resource locks. Fixed delay does not prevent two **different** jobs from modifying the same DB row.

## 13. Common Mistakes and Fixes

| Misconception / Symptom | Real Cause | Fix |
| --- | --- | --- |
| “delay=5s means starting every 5s” | Fixed delay counts from **completion** of the previous run | Use fixed rate if you need cadence from start times |
| First run executes immediately, thinking scheduler skipped 5s | Overload without `startTime` starts as soon as possible | Specify `Instant` first run or `@Scheduled(initialDelay=...)` |
| Next run is later than 5s | Delay is a minimum threshold, not a start-time SLA | Measure worker contention, load, GC, pause/resume |
| Increasing pool size still doesn't overlap one job | Each periodic registration runs sequentially under fixed delay | This is per contract; use a different design for parallel batches |
| Schedule keeps running despite task throwing exception | Spring default repeating ErrorHandler usually suppresses errors | Track failed runs, configure an intentional error policy |
| Schedule stops after exception in raw JDK | JDK periodic scheduling suppresses subsequent runs | Handle errors inside the task or restart per policy |
| `ScheduledFuture.get()` never returns | Future represents the **periodic series**, not a single run | Use metrics/latches/job state, do not wait on `get` forever |
| Fixed delay yet reports still overlap | Task only submits a `CompletableFuture` and returns | Define a business-completion boundary, use a gate/lease |
| API must run at 02:00 sharp but drifts | Fixed delay adds processing duration | Use cron + timezone / job ledger |
| Three pods run three times | Each pod has its own scheduler | Distributed coordination, idempotency |
| One long scheduled job delays another job | Scheduler pool has too few workers | Separate schedulers by job type or grow pool carefully |
| Changed Boot execution core-size yet scheduler didn't change | Executor and scheduler are different abstractions/configs | Use scheduling properties or an explicit scheduler bean |
| Task hangs forever so no new run occurs | Missing I/O timeouts or task waiting on Future forever | Timeouts, deadlines, cancellation contracts |
| Switched to virtual threads and fixed-delay job bottlenecks | `SimpleAsyncTaskScheduler` fixed-delay uses a scheduler thread | Pick a suitable implementation/trigger, load-test |

## 14. Code Review Checklist

1. **Timing requirement:** does the system need to pause after completion, start every N seconds, or run at wall-clock marks?
2. **Implementation:** which `TaskScheduler` does the app use (`ThreadPoolTaskScheduler`, `SimpleAsyncTaskScheduler`, container-managed scheduler)?
3. **Overload:** are `Duration` and `Instant startTime` for the first run chosen properly? Is delay > 0 with clear units?
4. **Completion boundary:** does the `Runnable` execute full business work or only dispatch via `@Async` and return?
5. **Concurrency:** are there multiple registrations, duplicate `@Scheduled` annotations, or multiple pods causing unintended overlap?
6. **Error handling:** which policy is used, are errors logged/metered, and should the schedule stop on failure?
7. **Lifecycle:** who holds `ScheduledFuture`, who cancels it, and does shutdown wait/cancel tasks as required?
8. **Timeouts:** do network/DB calls and child Future waits have deadlines so one run cannot hang forever?
9. **Observability:** are last success, failure rate, duration, scheduling lag, and post-restart runs tracked?
10. **State:** are cursors/checkpoints/idempotency persisted durably when a run produces side effects?
11. **Capacity:** are pool size and co-located jobs sufficient to avoid starving critical jobs?
12. **Validation:** are there latch tests proving the post-completion pause, exception tests, and multi-instance tests?

## 15. Self-Check Questions

1. Run A starts at 09:00:00 and finishes at 09:00:11. When is the earliest `scheduleWithFixedDelay(..., Duration.ofSeconds(4))` can start Run B if uninhibited by load?
2. Why can `scheduleWithFixedDelay(task, Duration.ofSeconds(5))` run the first iteration immediately, while the overload with `Instant` waits until the specified time?
3. What is the difference between fixed delay and fixed rate when a run takes longer than the period?
4. Does increasing `ThreadPoolTaskScheduler.poolSize` from 1 to 8 cause **the same periodic task** to overlap itself?
5. A `@Scheduled(fixedDelay=5s)` method calls an `@Async` method on another bean and returns immediately. From what moment is the 5s pause measured?
6. Why can `handle.get()` on a periodic `ScheduledFuture` wait forever?
7. How does an exception in a raw JDK periodic Runnable compare with default Spring `ThreadPoolTaskScheduler` regarding subsequent runs?
8. If a task calls an external API with no read timeout and hangs, does fixed delay automatically start the next run?
9. Do three pods all running `@Scheduled` fixed delay automatically coordinate so only one pod processes?
10. When is cron more suitable than fixed delay, and why must cursors/checkpoints be stored separately?

**Takeaway:** `scheduleWithFixedDelay()` means **“finish work → pause for full delay → start next run when resources allow”**. The previous run's duration shifts the spacing between start times. This mechanism protects a polling series from overlapping itself and chasing schedules, yet **does not** replace timeouts, error handling, distributed locks, idempotency, or business outcome tracking.

## Official Documentation

- [Spring Framework 6.2 — TaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework 6.2 — @Scheduled Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)
- [Spring Framework 6.2 — TaskUtils, error handling for repeating tasks](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/TaskUtils.html)
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
