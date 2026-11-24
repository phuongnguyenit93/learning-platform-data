# ConcurrentTaskScheduler Adapts a JDK Scheduler

## 1. The Problem: You Already Have a JDK Scheduler and Want the Spring Interface

In Java, `ScheduledExecutorService` is the standard API for scheduling `Runnable` or `Callable` execution after a delay, at a **fixed rate**, or with a **fixed delay**. In Spring Framework, `TaskScheduler` is the abstraction serving the same purpose while adding methods accepting `Instant`, `Duration`, `Trigger`, and integrating with Spring configuration.

If an application **already has a `ScheduledExecutorService` supplied by the JDK or another environment**, you do not necessarily have to rewrite the scheduler. **`ConcurrentTaskScheduler`** is an adapter accepting a `java.util.concurrent.ScheduledExecutorService` and **exposing the `org.springframework.scheduling.TaskScheduler` interface** to Spring components.

~~~text
Spring Application
       |
       |  TaskScheduler.schedule(task, Instant)
       |  TaskScheduler.schedule(task, Trigger)
       |  TaskScheduler.scheduleAtFixedRate(task, Duration)
       v
+------------------------------+
| ConcurrentTaskScheduler      |  <- Spring adapter
| - translates schedule to JDK scheduling |
| - supports Spring Trigger    |
| - handles task errors        |
+---------------+--------------+
                |
                | delegate
                v
+------------------------------+
| ScheduledExecutorService     |  <- JDK execution resource
| typically ScheduledThreadPool|
| Executor                     |
+---------------+--------------+
                |
                v
             worker threads
~~~

**Important reminder:** an adapter does not turn `ScheduledExecutorService` into a durable scheduler or automatically create transactions. Worker count, thread factory, shutdown policy, task acceptance, and load capacity **still depend on the underlying executor**. Lifecycle configuration must make clear which component owns the executor.

This article belongs to the **Scheduler Selection** group of **Spring Framework – Concurrency**. It focuses on how `ConcurrentTaskScheduler` adapts the JDK, API usage, trigger scheduling, lifecycle, comparison with `ThreadPoolTaskScheduler`, and a runnable Java 17 + Spring example.

## 2. Two Interfaces: ScheduledExecutorService and TaskScheduler

### 2.1. JDK ScheduledExecutorService

`ScheduledExecutorService` extends `ExecutorService`. Commonly used APIs:

~~~java
ScheduledFuture<?> oneTime =
        scheduledExecutor.schedule(task, 2, TimeUnit.SECONDS);

ScheduledFuture<?> fixedRate =
        scheduledExecutor.scheduleAtFixedRate(
                task, 1, 5, TimeUnit.SECONDS);

ScheduledFuture<?> fixedDelay =
        scheduledExecutor.scheduleWithFixedDelay(
                task, 1, 5, TimeUnit.SECONDS);
~~~

This is an **illustrative code fragment**, requiring `scheduledExecutor`, `task`, and `java.util.concurrent` imports. The time arguments in the JDK APIs above are **relative delays** in the given time unit.

- `schedule`: runs **once** after the requested delay.
- `scheduleAtFixedRate`: repeats on a cadence based on expected start times and period.
- `scheduleWithFixedDelay`: repeats with a wait interval between **previous run completion** and **next run start**.
- `ScheduledFuture`: allows tracking completion/cancellation. For normal periodic tasks, it does not complete successfully like a one-shot future; cancel it when no longer needed.

For a single periodic task scheduled through the JDK via `scheduleAtFixedRate` or `scheduleWithFixedDelay`, runs **do not overlap themselves** under the `ScheduledThreadPoolExecutor` contract; if one run takes too long, subsequent runs may be delayed. **Different tasks** can still run concurrently if the pool has enough threads.

### 2.2. Spring TaskScheduler

The `TaskScheduler` interface (Spring Framework 6.1) primarily defines:

~~~java
Clock getClock();

ScheduledFuture<?> schedule(Runnable task, Instant startTime);

ScheduledFuture<?> schedule(Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
~~~

This is an **illustrative signature excerpt**, not a complete Java class. Unlike the JDK, Spring accepts `Instant` (an absolute timestamp), `Duration` (an interval), and `Trigger` (computing the next run dynamically from schedule context).

Both abstractions separate **scheduling intent** from **thread provisioning and execution**. Business code can depend on `TaskScheduler` and run against a JDK backend in simple setups, a container-managed backend in Jakarta EE, or a bean-configured Spring backend.

### 2.3. Comparison Table

| Need | JDK ScheduledExecutorService | Spring TaskScheduler |
| --- | --- | --- |
| Run once after a delay | `schedule(command, delay, unit)` | `schedule(command, Instant)` |
| Fixed rate | `scheduleAtFixedRate(command, initialDelay, period, unit)` | `scheduleAtFixedRate(command, Duration)` or with `Instant` |
| Fixed delay | `scheduleWithFixedDelay(command, initialDelay, delay, unit)` | `scheduleWithFixedDelay(command, Duration)` or with `Instant` |
| Cron-based schedule | No direct built-in Cron API | `schedule(task, new CronTrigger(...))` |
| Custom schedule based on prior run | Must implement orchestration logic manually | `schedule(task, Trigger)` |
| Cancel schedule | `ScheduledFuture.cancel(...)` | `ScheduledFuture.cancel(...)` |
| Thread pool and lifecycle | Configure/manage concrete executor | Depends on implementation or delegate resource |

`ConcurrentTaskScheduler` bridges the two so Spring code uses the right-hand column while the backend is a JDK object from the left-hand column.

## 3. What Does ConcurrentTaskScheduler Actually Do?

`org.springframework.scheduling.concurrent.ConcurrentTaskScheduler` extends `ConcurrentTaskExecutor` and implements `TaskScheduler`. Thus it can function as a `TaskExecutor`/`SchedulingTaskExecutor` for regular tasks while also providing the scheduling API.

On the **TaskScheduler** branch, it forwards calls to the configured `ScheduledExecutorService`. For `Trigger`-based schedules backed by a standard JDK scheduler, Spring computes the next execution time and **reschedules** on the JDK executor run by run.

~~~text
taskScheduler.schedule(task, springTrigger)
                   |
                   v
             Trigger.nextExecution(context)
                   |
                   v
        computes next execution time
                   |
                   v
        ScheduledExecutorService.schedule(...)
                   |
                   v
             Runnable completes
                   |
                   v
         updates TriggerContext
                   |
                   +----> computes/schedules next run
~~~

**Note:** with a **JSR-236/Jakarta Concurrency** `ManagedScheduledExecutorService` in a compatible environment, `ConcurrentTaskScheduler` detects it and can use container-managed Trigger scheduling instead of the local rescheduling loop. When running pure JDK as in this article's example, keep in mind it uses a standard `ScheduledExecutorService` backend.

The adapter also provides `setErrorHandler(...)` for task errors and `setClock(...)` to define the Clock used for schedule calculations. It is **not** a persistence layer, distributed scheduler, or guarantee of exact on-time execution under system saturation.

### 3.1. Constructors and Spring Versions

In Spring Framework 6.1, notable ways to instantiate it include:

~~~java
// Preferred when one JDK scheduler serves both roles.
ConcurrentTaskScheduler scheduler =
        new ConcurrentTaskScheduler(jdkScheduledExecutor);

// If you want different executors for regular tasks and scheduling:
ConcurrentTaskScheduler separated =
        new ConcurrentTaskScheduler(
                generalExecutor, jdkScheduledExecutor);
~~~

This is an **illustrative code fragment**; you must declare `generalExecutor` of type `Executor` and `jdkScheduledExecutor` of type `ScheduledExecutorService`.

The first constructor uses **the same `ScheduledExecutorService`** as the delegate for scheduling and, per the constructor contract, regular task execution calls. The second constructor takes **two separate delegates**: an `Executor` for `SchedulingTaskExecutor` calls and a `ScheduledExecutorService` for `TaskScheduler` methods.

The **no-arg constructor** still exists in Spring 6.1 but is **marked deprecated**; in new code, supply an explicit backend via constructor rather than relying on an implicit default scheduler.

A `setScheduledExecutor(ScheduledExecutorService)` method exists, but note it **only replaces the scheduling delegate**. If you want `ConcurrentTaskExecutor`'s `execute`/`submit` calls to target a different or matching backend, configure the concurrent executor branch accordingly (e.g., `setConcurrentExecutor(...)`) or use the two-argument constructor.

### 3.2. Do Not Confuse the Adapter with ThreadPoolTaskScheduler

`ThreadPoolTaskScheduler` is a Spring implementation that is usually more convenient when the application **wants Spring to configure and manage the pool** via bean-style properties such as pool size, thread name prefix, shutdown policies, and lifecycle integration. `ConcurrentTaskScheduler` fits when you **already have a `ScheduledExecutorService`** or must adapt a JDK implementation created under custom policies.

If you simply need a Spring-managed scheduler pool with no pre-existing JDK backend, `ThreadPoolTaskScheduler` typically takes less wiring. Choose the adapter to reuse an existing underlying resource, not out of a belief that the word "Concurrent" creates extra parallelism beyond the supplied pool.

## 4. Configuring Spring Beans with JDK ScheduledExecutorService

### 4.1. Create the Backend First, Then Wrap with the Adapter

~~~java
@Configuration(proxyBeanMethods = false)
public class SchedulingConfig {

    @Bean(destroyMethod = "shutdown")
    public ScheduledExecutorService jdkScheduledExecutor() {
        return Executors.newScheduledThreadPool(2);
    }

    @Bean("taskScheduler")
    public TaskScheduler taskScheduler(
            ScheduledExecutorService jdkScheduledExecutor) {
        return new ConcurrentTaskScheduler(jdkScheduledExecutor);
    }
}
~~~

This is a **configuration fragment**; import `Configuration`, `Bean`, `TaskScheduler`, `ConcurrentTaskScheduler`, `Executors`, and `ScheduledExecutorService`. It clearly shows **who manages the resource**: the JDK backend is a Spring bean, and `destroyMethod = "shutdown"` tells Spring to shut it down when the context closes.

When using an existing JDK executor in the application, register/wire that instance into the adapter bean instead of creating a second pool. If the executor is managed by an **application server**, calling `shutdown()` from a sub-application usually **violates resource ownership**. Let the container own the lifecycle.

**Do not call `new ConcurrentTaskScheduler()` and ignore shutting down an implicit executor.** In Spring 6.1 the no-arg constructor is deprecated; explicit dependencies and clear ownership help prevent thread leaks.

### 4.2. If Multiple ScheduledExecutorService Beans Exist

Constructor injection by type can be ambiguous. Use `@Qualifier`:

~~~java
@Bean("reportTaskScheduler")
public TaskScheduler reportTaskScheduler(
        @Qualifier("reportJdkExecutor")
        ScheduledExecutorService backend) {
    return new ConcurrentTaskScheduler(backend);
}
~~~

This is a configuration fragment assuming a `reportJdkExecutor` bean exists with appropriate imports. When multiple `TaskScheduler` beans exist, consumers should inject via qualifiers instead of relying on implicit selection.

Do not name multiple distinct beans `taskScheduler` and expect `@Scheduled` to pick the right one automatically: annotation routing depends on the context's scheduler selection configuration.

## 5. One-Shot Scheduling with Instant

The simplest API:

~~~java
ScheduledFuture<?> handle =
        taskScheduler.schedule(
                () -> System.out.println("once"),
                Instant.now().plusSeconds(10));
~~~

This is an illustrative Java snippet; `taskScheduler` must be an injected `TaskScheduler` reference. `Instant` represents **a point on the timeline**. Because the JDK backend expects a relative delay, the adapter computes the delay between the current `Clock` and the target timestamp before forwarding to the delegate.

What happens if `startTime` is already in the past? The scheduler normally executes as soon as possible according to scheduling delay rules; no specific nanosecond or millisecond precision is guaranteed. OS clock jumps, JVM pauses, busy pools, or backlogs can all shift actual execution time.

Note that `schedule(Runnable, Trigger)` can return **null** if the `Trigger` produces no next fire time; callers using `ScheduledFuture` must account for that. With `Instant` scheduling, a normal backend returns a cancellable handle.

## 6. Fixed Rate and Fixed Delay Through the Adapter

### 6.1. Fixed Rate: Expected Start Timestamps

~~~java
ScheduledFuture<?> fixedRate =
        taskScheduler.scheduleAtFixedRate(
                () -> refreshCache(),
                Duration.ofSeconds(5));
~~~

This snippet requires a matching `refreshCache()` method. "Fixed rate" means trying to preserve the **interval between expected start timestamps**, not guaranteeing every run starts on the dot. If a job takes longer than the period or the pool is busy, subsequent runs can be delayed.

### 6.2. Fixed Delay: Waiting After Completion

~~~java
ScheduledFuture<?> fixedDelay =
        taskScheduler.scheduleWithFixedDelay(
                () -> pullMessages(),
                Duration.ofSeconds(5));
~~~

This snippet requires `pullMessages()`. "Fixed delay" measures from **when the previous job finishes** to when the next job becomes eligible to start. If a job takes 12 seconds with a 5-second delay, the next run generally becomes eligible about 17 seconds after the previous run started (plus overhead).

### 6.3. Timeline Illustration

~~~text
A task takes about 3 units; period/delay = 5 units:

Fixed rate (expected start ticks: 0,5,10,...):
0    3  5    8 10   13
|====|  |====|  |====|
run 1   run 2   run 3

Fixed delay (wait interval after completion: 5):
0    3       8   11      16
|====|-------|===|-------|====
run 1  delay  run 2 delay  run 3
~~~

This is an ideal timeline with no system pressure. With a real pool, start times can lag. **Consecutive executions of the same periodic schedule** do not automatically overlap merely because the scheduler has multiple workers; **different** jobs can run concurrently if the pool has capacity.

### 6.4. Using Overloads with Instant

~~~java
Instant firstRun = Instant.now().plusSeconds(30);

ScheduledFuture<?> rate =
        taskScheduler.scheduleAtFixedRate(
                task, firstRun, Duration.ofMinutes(1));

ScheduledFuture<?> delay =
        taskScheduler.scheduleWithFixedDelay(
                task, firstRun, Duration.ofMinutes(1));
~~~

This illustrative snippet requires `task`. `firstRun` lets you choose the initial execution timestamp. Avoid confusing Spring's `Instant` overloads with JDK methods that take a relative `initialDelay`.

## 7. Trigger: A Key Capability When Adapting from JDK

`ScheduledExecutorService` by itself lacks a general API like "run according to this cron expression." Spring's `TaskScheduler.schedule(Runnable, Trigger)` fills that gap.

### 7.1. CronTrigger

~~~java
ScheduledFuture<?> cronJob =
        taskScheduler.schedule(
                () -> System.out.println("quarter-hour tick"),
                new CronTrigger("0 */15 * * * *"));
~~~

This is an illustrative snippet requiring `CronTrigger`; the expression uses Spring's **six-field** cron syntax, running at second 0 every 15 minutes. Set `zone` explicitly when business rules depend on a time zone:

~~~java
CronTrigger vietnamBusinessTime =
        new CronTrigger(
                "0 0 9 * * MON-FRI",
                ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

This is an illustrative code fragment; import `ZoneId`. It expresses a schedule at 09:00 every weekday in the chosen time zone (following Spring cron rules). `ZoneId` makes cron interpretation explicit when the app runs on servers in different time zones.

Do not use cron for millisecond-precision timing in unit tests. Second-based cron and calendar scheduling can be affected by time zones and daylight saving time (DST) transitions in certain regions.

### 7.2. PeriodicTrigger

~~~java
PeriodicTrigger trigger =
        new PeriodicTrigger(Duration.ofSeconds(10));

trigger.setInitialDelay(Duration.ofSeconds(2));
trigger.setFixedRate(false); // fixed-delay by default

ScheduledFuture<?> handle =
        taskScheduler.schedule(task, trigger);
~~~

This is an illustrative code fragment. `PeriodicTrigger` is useful when a component wants to accept an **abstract `Trigger`**, allowing `CronTrigger`, `PeriodicTrigger`, or a custom trigger to be swapped in. If your sole goal is fixed rate or fixed delay, calling `scheduleAtFixedRate`/`scheduleWithFixedDelay` directly is usually clearer.

### 7.3. Custom Trigger and TriggerContext

In Spring 6.1, `Trigger.nextExecution(TriggerContext)` returns an `Instant` (or null when no further run is scheduled):

~~~java
Trigger custom = context -> {
    Instant last = context.lastCompletion();

    if (last == null) {
        return context.getClock().instant().plusSeconds(3);
    }

    return last.plusSeconds(15);
};
~~~

This is an illustrative code fragment; when writing a custom trigger, check nullability, timestamps, and termination logic. `TriggerContext` provides `lastScheduledExecution()`, `lastActualExecution()`, `lastCompletion()`, and `getClock()`. After each run completes, Spring can consult the trigger for the next timestamp and reschedule on the JDK executor.

If the trigger returns `null`, the schedule ends per the trigger contract; do not treat that as a failure. A custom trigger that throws exceptions or computes invalid timestamps must be tested and handled per the API.

## 8. Runnable Example: Java 17, Spring Framework 6.1, and ScheduledExecutorService

This is a complete command-line project proving:

1. The Spring `TaskScheduler` bean is actually a **`ConcurrentTaskScheduler` wrapping a JDK `ScheduledExecutorService`**.
2. One-shot `schedule(..., Instant)` runs on a thread created by the JDK factory.
3. `scheduleAtFixedRate(..., Duration)` runs repeatedly without requiring `@EnableScheduling`.
4. `schedule(..., PeriodicTrigger)` runs repeatedly via Spring's Trigger mechanism.
5. `ScheduledFuture.cancel(false)` stops further periodic runs in the demo.
6. Spring shuts down the JDK executor when the `ApplicationContext` closes via the bean destroy method.

The demo uses **`CountDownLatch`** to verify execution counts and avoid guessing with arbitrary `Thread.sleep` delays. It prints no fluctuating thread names or timestamps; stdout prints deterministic booleans once tasks finish before the timeout.

**Environment:** JDK 17+, Gradle 8.5+ (or a Gradle version compatible with the project's JDK), Spring Framework 6.1.14.

### 8.1. Project Structure

~~~text
jdk-scheduler-adapter/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SchedulerAdapterDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jdk-scheduler-adapter'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.SchedulerAdapterDemo'
}
~~~

**src/main/java/demo/SchedulerAdapterDemo.java**

~~~java
package demo;

import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ConcurrentTaskScheduler;
import org.springframework.scheduling.support.PeriodicTrigger;

public final class SchedulerAdapterDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskScheduler scheduler = context.getBean(TaskScheduler.class);

            AtomicBoolean allUsedJdkThreads = new AtomicBoolean(true);
            CountDownLatch oneShotRan = new CountDownLatch(1);
            CountDownLatch fixedRanTwice = new CountDownLatch(2);
            CountDownLatch triggerRanTwice = new CountDownLatch(2);

            // Run once at an Instant.
            ScheduledFuture<?> oneShot = Objects.requireNonNull(
                    scheduler.schedule(() -> {
                        checkThread(allUsedJdkThreads);
                        oneShotRan.countDown();
                    }, Instant.now().plusMillis(20)));

            // Run repeatedly at a fixed rate.
            ScheduledFuture<?> fixedRate =
                    scheduler.scheduleAtFixedRate(() -> {
                        checkThread(allUsedJdkThreads);
                        fixedRanTwice.countDown();
                    }, Duration.ofMillis(30));

            // Spring Trigger executed through the JDK backend.
            PeriodicTrigger periodic =
                    new PeriodicTrigger(Duration.ofMillis(30));
            periodic.setInitialDelay(Duration.ZERO);

            ScheduledFuture<?> byTrigger = Objects.requireNonNull(
                    scheduler.schedule(() -> {
                        checkThread(allUsedJdkThreads);
                        triggerRanTwice.countDown();
                    }, periodic));

            try {
                oneShot.get(5, TimeUnit.SECONDS);

                if (!fixedRanTwice.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Fixed-rate timeout");
                }
                if (!triggerRanTwice.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Trigger timeout");
                }

                System.out.println("one-shot fired: " +
                        (oneShotRan.getCount() == 0));
                System.out.println("fixed-rate fired twice: " +
                        (fixedRanTwice.getCount() == 0));
                System.out.println("trigger fired twice: " +
                        (triggerRanTwice.getCount() == 0));
                System.out.println("JDK threads used: " +
                        allUsedJdkThreads.get());
            } finally {
                // Cancel periodic schedules; no need to interrupt running tasks.
                fixedRate.cancel(false);
                byTrigger.cancel(false);
            }
        }
    }

    private static void checkThread(AtomicBoolean observed) {
        if (!Thread.currentThread().getName()
                .startsWith("jdk-scheduler-")) {
            observed.set(false);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(destroyMethod = "shutdown")
        public ScheduledExecutorService jdkScheduledExecutor() {
            AtomicInteger sequence = new AtomicInteger();

            return Executors.newScheduledThreadPool(2, command ->
                    new Thread(command, "jdk-scheduler-" +
                            sequence.incrementAndGet()));
        }

        @Bean("taskScheduler")
        public TaskScheduler taskScheduler(
                ScheduledExecutorService jdkScheduledExecutor) {

            return new ConcurrentTaskScheduler(jdkScheduledExecutor);
        }
    }
}
~~~

### 8.2. Running and Output

From the `jdk-scheduler-adapter` directory, with Java 17+ and Gradle installed:

~~~bash
gradle run
~~~

If the project includes the Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

**Stdout lines printed by the program itself on a successful run**:

~~~text
one-shot fired: true
fixed-rate fired twice: true
trigger fired twice: true
JDK threads used: true
~~~

Additional output may be printed by Gradle or Spring. The "twice" checks here are **test conditions** (CountDownLatch reaching 0), not assertions that tasks ran exactly twice. Periodic schedules may fire additional times while the caller observes them before cancellation; that does not affect the booleans. If the environment is overloaded or the scheduler fails to run within 5 seconds, the program throws an exception rather than reporting false success.

### 8.3. Why Does This Example Prove the Adapter?

- The **JDK `ScheduledExecutorService`** thread factory explicitly sets the `jdk-scheduler-` prefix; every task run verifies that prefix.
- Spring **does not create a second thread pool**: `new ConcurrentTaskScheduler(jdkScheduledExecutor)` receives the exact delegate from the bean.
- `TaskScheduler.schedule(..., Instant)` performs one-shot scheduling.
- `scheduleAtFixedRate(..., Duration)` delegates to the scheduling backend.
- `schedule(..., PeriodicTrigger)` uses Spring's `Trigger` abstraction alongside the JDK scheduling backend.
- `oneShot.get(timeout)` ensures the one-shot task finished before printing results; latches for the periodic tasks confirm each fired at least twice.
- `finally` cancels the fixed-rate and trigger schedules. `@Bean(destroyMethod="shutdown")` ties the JDK backend's lifecycle to the Spring context; the adapter is not forced to shut down a pool it does not own.
- There is no `@EnableScheduling` because the code **calls the `TaskScheduler` API directly** rather than using `@Scheduled`. If you add annotation-driven scheduling, enable the corresponding infrastructure as shown in Section 9.

## 9. Integrating with @Scheduled: Manual vs. Annotation-Driven Scheduling

### 9.1. TaskScheduler Does Not Automatically Enable @Scheduled

This call registers a schedule directly when executed:

~~~java
taskScheduler.scheduleAtFixedRate(
        this::refreshIndex, Duration.ofMinutes(1));
~~~

This illustrative snippet requires a class with a `refreshIndex` method. Enabling `@EnableScheduling` is **not mandatory** solely to call `TaskScheduler` directly.

Conversely, this annotation:

~~~java
@Component
class MaintenanceJobs {
    @Scheduled(fixedDelay = 60000)
    public void refreshIndex() {
        // Perform work.
    }
}
~~~

requires Spring imports, bean component scanning, and **`@EnableScheduling`** in the `ApplicationContext`. Annotations do not activate automatically just because a `ConcurrentTaskScheduler` bean exists.

### 9.2. Explicitly Selecting TaskScheduler for Annotation-Driven Scheduling

In simple setups, Spring's scheduling infrastructure looks up a unique `TaskScheduler` or a bean named `taskScheduler` according to the version's rules. Explicit configuration helps when multiple schedulers exist:

~~~java
@Configuration
@EnableScheduling
public class ScheduledJobsConfig implements SchedulingConfigurer {

    private final TaskScheduler adapter;

    public ScheduledJobsConfig(
            @Qualifier("reportTaskScheduler") TaskScheduler adapter) {
        this.adapter = adapter;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar registrar) {
        registrar.setTaskScheduler(adapter);
    }
}
~~~

This is a **configuration fragment**, requiring imports for `@Configuration`, `@EnableScheduling`, `SchedulingConfigurer`, `ScheduledTaskRegistrar`, `@Qualifier`, and a `reportTaskScheduler` bean. It routes `@Scheduled` tasks through the desired scheduler rather than relying on ambiguous bean selection.

`@Async` is a separate mechanism: it requires `@EnableAsync` (or equivalent configuration) and an appropriate executor. Having a `ConcurrentTaskScheduler` **does not make all `@Async` methods run on a schedule automatically**. `@Scheduled` determines **when** a method is triggered; `@Async` determines **how** a method call is dispatched when intercepted by a Spring proxy. The two concepts can work together, but you must verify thread counts, ordering, rejections, and exception handling.

### 9.3. Avoid Registering the Same Schedule Twice

If an action already has `@Scheduled`, and you also call `scheduler.schedule(...)` for it at startup, the application can create **two independent schedules**. This incident is often mistaken for Spring invoking the method twice. Before patching with a lock, check how many registrations were actually created and who owns each `ScheduledFuture`.

## 10. Managing the JDK Backend Lifecycle

### 10.1. Whoever Creates the Executor Must Own Its Shutdown Policy

A `ScheduledExecutorService` created by `Executors.newScheduledThreadPool(...)` holds worker threads and pending schedules. If you simply pass it to an adapter and drop its reference/lifecycle, the JVM may fail to exit and schedules can keep running after the business component is no longer needed.

Valid approaches:

- In Spring, expose `ScheduledExecutorService` as a bean and declare `destroyMethod = "shutdown"` or an appropriate destroy strategy.
- If code creates a pool outside the container, close it in `finally` via `shutdown()` or `shutdownNow()` per its contract.
- If the backend is provided by Jakarta EE/the container, **do not shut down a server-wide resource** from application code; let the environment manage its lifecycle.
- If registering a schedule dynamically on user request, retain the `ScheduledFuture` so you can cancel it when the request is removed.

### 10.2. shutdown vs. shutdownNow

~~~java
ScheduledExecutorService backend =
        Executors.newScheduledThreadPool(2);

try {
    // Register and use schedules.
} finally {
    backend.shutdown();
    if (!backend.awaitTermination(5, TimeUnit.SECONDS)) {
        backend.shutdownNow();
    }
}
~~~

This is an illustrative snippet placed inside a method with `throws InterruptedException` or proper catching; not a standalone class. `shutdown()` stops accepting new tasks and handles remaining tasks per the implementation's shutdown policies; `shutdownNow()` attempts to interrupt workers and returns pending unexecuted tasks. **Neither API promises that every callback stopped safely or that side effects rolled back.**

If the thread waiting in `awaitTermination` is interrupted, handle `InterruptedException` per contract (typically calling `shutdownNow` if you truly own the backend, then restoring interrupt status or propagating).

### 10.3. ScheduledThreadPoolExecutor Shutdown Policies

When fine-grained control is needed, use `ScheduledThreadPoolExecutor` directly instead of a generic factory. It exposes properties such as:

- `setRemoveOnCancelPolicy(true)`: purges cancelled delayed tasks from the delay queue per policy to reduce object retention.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(...)`: decides whether pending delayed tasks run after shutdown.
- `setContinueExistingPeriodicTasksAfterShutdownPolicy(...)`: decides whether existing periodic tasks continue after shutdown per policy.

These options must be tested against your shutdown SLA. Do not assume aggressive policies like "always cancel every task" merely because `ConcurrentTaskScheduler` is declared: **the underlying executor** determines most of the real lifecycle behavior.

## 11. Cancellation, ScheduledFuture, and Cancelling a Schedule

`TaskScheduler` returns `ScheduledFuture<?>` so the caller can cancel a schedule:

~~~java
ScheduledFuture<?> handle =
        scheduler.scheduleAtFixedRate(
                this::runMaintenance, Duration.ofMinutes(10));

// When you no longer want subsequent runs:
boolean cancellationRequested = handle.cancel(false);
~~~

This is an illustrative snippet. With `cancel(false)`, code does not request interrupting an active run. `cancel(true)` can request interrupting the worker if the implementation supports it, yet **does not guarantee** a task executing JDBC/HTTP or external side effects stops immediately.

Important distinctions:

- **Cancelling a schedule** and **cancelling a business job** are not identical. One run may already have kicked off another background task.
- A periodic schedule may have already run several times before cancellation; `cancel` only takes effect per contract at the time of the call.
- `ScheduledFuture.isCancelled()` reports the handle's state; it does not prove downstream operations rolled back.
- With a custom `Trigger`, Spring's scheduler can schedule new runs after each completion; hold onto **the handle returned by `TaskScheduler.schedule(..., trigger)`** rather than cancelling an internal task that the adapter might keep rescheduling.
- Never call `get()` without a timeout on a periodic Future meant to run forever; it may never complete normally.

When a task truly has a deadline, add I/O timeouts, cancellation tokens, or job state tracking rather than relying solely on the scheduled future.

## 12. Task Error Handling: Spring Adapter vs. JDK Behavior

### 12.1. Exceptions in a Scheduled Runnable

With JDK `ScheduledExecutorService.scheduleAtFixedRate` directly, if an execution throws an unhandled exception, subsequent runs of the periodic schedule are **suppressed** (stopped) per the JDK contract.

`ConcurrentTaskScheduler` provides `setErrorHandler(ErrorHandler)` and uses Spring's wrapper around scheduled tasks. Under Spring's default configuration, **repeating tasks** typically log and **suppress exceptions** so the schedule continues; **one-shot tasks** typically log and propagate exceptions so they surface on the Future. Configuring a custom handler can change this behavior significantly.

~~~java
ConcurrentTaskScheduler adapter =
        new ConcurrentTaskScheduler(jdkBackend);

adapter.setErrorHandler(error -> {
    // Record metric, rate-limited log, update task status.
    recordScheduledFailure(error);

    // If rethrown here, the schedule may stop per policy.
});
~~~

This is an illustrative fragment; `jdkBackend` and `recordScheduledFailure` are undefined. Never use a handler that silently swallows all errors when the business needs to know a job failed; equally, never blindly rethrow on every periodic callback without understanding that it can halt the schedule.

### 12.2. Rejection at Schedule Time

When `ScheduledExecutorService` has shut down or can accept no more work, `schedule` can throw `RejectedExecutionException`. Through Spring's API, `ConcurrentTaskScheduler` can translate that into `TaskRejectedException` per Spring's contract.

**Distinguish the two phases**:

~~~text
scheduler.schedule(task, time)
        |
        +-- Rejected at registration? -> error immediately at caller
        |
        +-- Accepted -> ScheduledFuture
                         |
                         +-- task runs and succeeds
                         +-- task fails, handled by ErrorHandler
                         +-- handle cancelled
                         +-- backend shutdown / process crash
~~~

Receiving a `ScheduledFuture` **does not mean** the system guarantees the task will run on time, complete, or survive a restart. Track **registrations**, **actual starts**, **completed/failed**, **cancelled**, and **missed deadlines** according to business needs.

### 12.3. @Scheduled and AsyncUncaughtExceptionHandler Are Not the Same

`AsyncUncaughtExceptionHandler` applies primarily to `@Async void` methods. It is not a general error-handling solution for methods invoked by `TaskScheduler`. Scheduled runnables use the scheduler's error handling; production systems should place explicit logging/metrics policies at **the right layer**.

## 13. Comparing Spring Scheduler Options

| Option | Primary backend | When is it suitable? | Notes |
| --- | --- | --- | --- |
| `ConcurrentTaskScheduler` | App- or container-supplied `ScheduledExecutorService` | Already have a JDK scheduler and want Spring `TaskScheduler`/Trigger | Pool lifecycle depends on owner; configure explicitly |
| `ThreadPoolTaskScheduler` | Spring-managed `ScheduledThreadPoolExecutor` underneath | Want Spring bean config for pool, naming, shutdown | Often simpler when starting from scratch |
| `DefaultManagedTaskScheduler` | Managed scheduler from Jakarta EE/container, usually via JNDI | Environments forbidding app-owned threads | Server manages lifecycle |
| `SimpleAsyncTaskScheduler` (Spring 6.1+) | One coordinating scheduler thread, spawning execution threads by model | Simple scheduler needs, usable with JDK 21 virtual threads | Fixed-delay runs on a single scheduler thread by design; evaluate blocking tasks |
| Plain JDK `ScheduledExecutorService` | ScheduledExecutorService | Need Java scheduling without Spring Trigger/DI | No `TaskScheduler` abstraction for Spring components |
| Quartz | Specialized scheduler | Complex schedules/persistent jobs, multi-node depending on config | Higher setup and ops complexity; durability depends on JobStore/config |

**Selection guidance:** if you need to adapt an existing executor, choose `ConcurrentTaskScheduler`. If you want a standard Spring-managed scheduler pool with convenient lifecycle, choose `ThreadPoolTaskScheduler`. If schedules must **recover after crashes**, persist job definitions, or coordinate across multiple nodes, evaluate a specialized scheduler/job store instead of relying on an in-memory `ScheduledExecutorService`.

## 14. Actual Concurrency Depends on the Executor

The name `ConcurrentTaskScheduler` can mislead: it **does not** guarantee all schedules run concurrently. If the backend is:

~~~java
ScheduledExecutorService single =
        Executors.newSingleThreadScheduledExecutor();

TaskScheduler adapter = new ConcurrentTaskScheduler(single);
~~~

All scheduled tasks share **one worker**, so a long blocking callback can delay every remaining schedule. With a two-thread backend pool, actual max concurrency still depends on the real worker count and how jobs consume resources.

### 14.1. Distinguishing the Scheduling Thread from Offloaded Work

A scheduled callback can either:

1. Run the work directly, holding the scheduler worker until done.
2. Simply create a job/submit to another `TaskExecutor` and return, freeing the scheduler thread early.

The second pattern helps the scheduler keep dispatching triggers on time when jobs are heavy, yet introduces **two layers of queueing, rejection, and lifecycle**. You must manage the target task executor; the callback returning does not automatically mean the job finished.

~~~text
JDK ScheduledExecutorService
         |
         +-- trigger: runs short Runnable
                          |
                          +--> TaskExecutor.execute(heavyTask)
                                        |
                                        +--> separate worker pool
~~~

If `heavyTask` is critical, `execute` succeeding does not guarantee durable delivery. Use a job store, outbox, or broker when persistence is required.

### 14.2. Downstream Bottlenecks Can Stall the Pool

Even with `newScheduledThreadPool(8)`, eight jobs waiting on a single DB connection will not increase throughput. Common bottlenecks include:

- A JDBC connection pool smaller than the number of concurrent jobs needing connections.
- Remote API rate limits or HTTP connection caps.
- Locks on singleton mutable state.
- Schedules sharing identical fire times, creating bursts.
- Cron jobs firing during peak traffic hours.
- Callbacks with infinite retries, long sleeps/blocks, or missing timeouts.

Use bounded concurrency, timeouts, capped retries, and monitor queue wait and deadline lag. Never raise thread counts blindly to fix every delayed schedule.

## 15. Cron, Clock, Time Zones, and Time Shifts

`ConcurrentTaskScheduler.setClock(Clock)` sets the `Clock` used to calculate schedule timestamps, defaulting to the system clock in the process's default time zone. `getClock()` returns that Clock per `TaskScheduler`.

~~~java
ConcurrentTaskScheduler adapter =
        new ConcurrentTaskScheduler(jdkBackend);

adapter.setClock(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

This illustrative snippet requires `Clock` and `ZoneId` imports; `jdkBackend` is already created. This configures the adapter's clock; do not mistake it for changing the OS clock or replacing `ScheduledExecutorService`'s monotonic timer implementation.

For business-timezone cron jobs, **explicitly specify `ZoneId` on `CronTrigger`** to state intent clearly. Cron can exhibit edge cases in regions with DST when hours are skipped or repeated; verify policies and expectations against the real time zone.

`Instant` is an absolute timestamp; `Duration` represents an elapsed length of time. When relying on historical calendars and business hours, use `CronTrigger`/Clock appropriately; when you just need "every n seconds," fixed-rate/fixed-delay and `Duration` are usually clearer.

**Testing time:** You can supply a mock `Clock` to test trigger-time computation logic, but changing only the adapter's Clock **does not advance the JDK worker's internal timer**. Integration tests may still need `CountDownLatch`, bounded timeouts, and instrumentation to prove real task execution.

## 16. Monitoring and Operational Safeguards

Measure at least:

- **scheduled registrations**: number of active one-shot/periodic schedules.
- **next planned execution**: next expected fire time (when exposed by the abstraction/registry).
- **actual start** and **completion time**: lag between planned and actual.
- **execution duration**, error count, cancellation count, and rejection count.
- **active workers**, queue depth, and task wait time on `ScheduledThreadPoolExecutor`.
- **retry/overlap state** if callbacks offload work to another pool.
- **shutdown duration** and pending schedules before application exit.

With a concrete `ScheduledThreadPoolExecutor`, you can inspect pool/queue state via JDK APIs or a metrics framework. With an abstract `ScheduledExecutorService`, not every implementation exposes pool size or queue depth identically; **do not blindly cast** to `ScheduledThreadPoolExecutor` when the backend comes from an external environment.

Naming threads via `ThreadFactory` (like `jdk-scheduler-` in the demo) makes thread dumps and logs clearer. In production, add structured logging, job IDs, and correlation IDs. Never put tokens or PII into thread names; pooled threads are reused across many different jobs.

### 16.1. A Scheduler Does Not Guarantee Exactly-Once Execution

Suppose a job sends an email at 09:00. If the JVM stops at 08:59 and restarts at 09:05, an in-memory schedule **will not automatically recover the missed 09:00 run**. Nor is a `ScheduledFuture` confirmation that the email reached the recipient.

For critical jobs:

1. Persist schedule definitions or job due times in a DB/job store.
2. Implement claim/lease mechanics when multiple nodes run.
3. Track pending/running/succeeded/failed/missed states.
4. Retry with an idempotency key or deduplication.
5. Define whether catch-up (misfire handling) runs after a restart.
6. Distinguish trigger firing from committed side effects.

`ConcurrentTaskScheduler` is only an adapter for in-process scheduling; it **does not replace** those durable job-execution mechanisms.

## 17. Anti-Patterns and Fixes

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| Using no-arg `new ConcurrentTaskScheduler()` in Spring 6.1 and forgetting the pool | Deprecated constructor, unclear lifecycle | Inject `ScheduledExecutorService` explicitly |
| Adapter bean creating `Executors.newScheduledThreadPool()` internally unmanaged | Thread leak, unclear shutdown | Declare the JDK executor as a bean with a destroy method |
| Assuming `setScheduledExecutor` also changes `execute` | Confuses the adapter's two delegates | Use the appropriate constructor or configure `setConcurrentExecutor` |
| One scheduler worker running very long blocking jobs | Other schedules lag | Size capacity appropriately or offload to a separate bounded worker pool |
| Putting `@Scheduled` without enabling `@EnableScheduling` | Annotations never register | Enable scheduling in the right context |
| Manually scheduling the same method already marked `@Scheduled` | Duplicate job runs | Choose a single scheduling mechanism |
| Assuming fixed rate is always on time or always overlaps | Overload, wrong expectations | Measure lag, set timeouts, tune period and pool |
| Using cron without a zone for local business hours | Time drift when deployed on differently configured servers | Specify `ZoneId` |
| Catching exceptions and ignoring them without metrics | Silent job failures | Clear `ErrorHandler` and observability |
| Catching errors and always rethrowing in periodic callbacks | Can halt the schedule | Decide stop/retry/continue by contract |
| Calling `future.get()` without timeout on a periodic schedule | Caller can hang | Use cancellation/status instead of waiting for normal completion |
| Treating `cancel(true)` as guaranteed worker termination | Side effects may keep running | Cooperative cancellation and downstream timeouts |
| Submitting new tasks while the executor is shutting down | Tasks get rejected | Manage producer/lifecycle, handle rejections |
| Using the adapter expecting schedules to survive restarts | In-memory state is lost | Durable job store/Quartz/outbox as required |
| Sharing a system-wide `ScheduledExecutorService` and shutting it down from a sub-app | Disrupts other consumers | Respect container resource ownership |

## 18. Checklist When Choosing ConcurrentTaskScheduler

- [ ] The application **already has** a `ScheduledExecutorService` or needs its specific behavior.
- [ ] Distinguished `TaskScheduler` from `TaskExecutor`; chose the one- or two-delegate constructor intentionally.
- [ ] The deprecated 6.1 no-arg constructor is not used in new code.
- [ ] The backend is provided via DI, not silently spawned on every schedule registration.
- [ ] Cron schedules include an explicit time zone when needed; fixed periods use `Duration`, timestamps use `Instant`.
- [ ] Clear rule for `@EnableScheduling` with `@Scheduled`, separate from programmatic API calls.
- [ ] When multiple scheduler beans exist, `@Qualifier` or `SchedulingConfigurer` is configured.
- [ ] An explicit owner shuts down the JDK executor at context/app exit; never shut down a shared container-wide backend improperly.
- [ ] Chosen pool size/thread factory considering DB/HTTP downstream capacity.
- [ ] Retain `ScheduledFuture` and cancellation logic for dynamic schedules.
- [ ] Defined an exception policy for scheduled tasks rather than guessing continuation vs. stopping.
- [ ] Catch/observe task rejections on executor shutdown or saturation.
- [ ] Never call `get()` indefinitely on periodic Futures.
- [ ] Collect metrics for execution lag, duration, errors, and cancellations.
- [ ] Do not treat an in-memory scheduler as a durable job store.
- [ ] Tests use latches/timeouts and cleanup rather than relying purely on `Thread.sleep`.

## 19. Self-Check Questions

1. **Which JDK interface does `ConcurrentTaskScheduler` adapt?** `ScheduledExecutorService`, to expose Spring's `TaskScheduler` API.
2. **Does the adapter create a pool itself when using the one-argument constructor?** No. It uses the supplied executor.
3. **What two purposes does the two-argument constructor represent?** One `Executor` for general task execution, and one `ScheduledExecutorService` for scheduling.
4. **Does `setScheduledExecutor` necessarily change the `execute` delegate?** No; it affects the `TaskScheduler` branch, without automatically changing the concurrent delegate.
5. **Why use Spring `Trigger` when the JDK already has `scheduleAtFixedRate`?** `Trigger` supports cron, time-based conditions, and schedules computed from prior run context.
6. **Does `PeriodicTrigger` default to fixed rate or fixed delay?** Fixed delay; it can be switched with `setFixedRate(true)`.
7. **In fixed delay, from when is the delay interval measured?** From when the previous run finishes to the next execution timestamp.
8. **If a periodic task runs long, does fixed rate overlap itself?** Per the JDK `ScheduledThreadPoolExecutor` contract, executions of the same periodic schedule do not overlap; they may be delayed.
9. **If a `TaskScheduler` bean exists, does `@Scheduled` work automatically?** Not yet; scheduling annotation infrastructure such as `@EnableScheduling` is needed in the appropriate context.
10. **Is `@EnableScheduling` required to call `schedule(task, trigger)`?** No; that is a direct API call.
11. **Who must shut down the JDK scheduled executor?** The component owning the resource (bean/app/container) per its lifecycle, not arbitrarily by every consumer.
12. **What does `setErrorHandler` affect?** How exceptions from scheduled tasks are handled; it can determine whether failed tasks are recorded and whether the schedule continues or stops.
13. **Does `cancel(false)` guarantee cancelling all side effects of a running job?** No; by parameter contract it does not even request interrupting an active task.
14. **Why is `schedule(..., CronTrigger)` sensitive to time zones?** Cron expresses calendar-based schedules; a zone is needed to interpret business hours accurately.
15. **Should you choose `ConcurrentTaskScheduler` or `ThreadPoolTaskScheduler` when starting a project from scratch?** Without a custom JDK backend, `ThreadPoolTaskScheduler` is usually more convenient for configuring pools and lifecycle.
16. **If schedules must survive a JVM restart, is `ConcurrentTaskScheduler` enough?** No; you need durable scheduling/a job store and misfire/retry/idempotency rules.
17. **How can you verify the adapter uses the intended JDK workers?** Name threads via a `ThreadFactory`, run a test task through `TaskScheduler`, and inspect thread prefixes/metrics.
18. **Why does the name Concurrent not mean every schedule runs in parallel?** Actual capacity depends on the JDK executor and shared resources, locks, and downstream limits.
19. **Can Jakarta EE's `ManagedScheduledExecutorService` be used?** Yes, in compatible environments; the adapter detects it. Lifecycle management belongs to the container.
20. **How do you prevent a cron job from running twice in an application?** Check for duplicate annotation and programmatic registrations or multiple instances/nodes running; cluster-wide single execution requires higher-level coordination.

**Conclusion:** `ConcurrentTaskScheduler` is **a bridge from JDK `ScheduledExecutorService` to Spring `TaskScheduler`**, adding Spring APIs for `Instant`, `Duration`, and `Trigger` on top of an existing JDK backend. Choose it when you need **to adapt an external executor**; use `ThreadPoolTaskScheduler` when you want Spring to manage the scheduler pool itself. Either way, manage **lifecycle, cancellation, error handling, concurrency, and durability** according to your application's contract.

### Official References

- [Spring Framework 6.1 — ConcurrentTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ConcurrentTaskScheduler.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.1 — TaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework 6.1 — PeriodicTrigger](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/support/PeriodicTrigger.html)
- [Spring Framework 6.1 — CronTrigger](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html)
- [Spring Framework 6.1 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Java 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
- [Java 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)
