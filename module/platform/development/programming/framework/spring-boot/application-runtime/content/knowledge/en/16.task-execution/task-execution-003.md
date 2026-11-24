# Using Spring-Managed `TaskExecutor` or `TaskScheduler` — Spring Boot 3.3

## 1. Goal and context

A Spring Boot application does not only run work on HTTP request threads. It may need to sync data, send notifications, process files, run background computations, perform periodic health checks, or run a report at 09:00. If each service creates its own `new Thread(...)` or `Executors.newFixedThreadPool(...)`, resource management becomes difficult: thread pools are not closed on time, tasks are lost on shutdown, thread counts grow unchecked, exceptions go unobserved, and schedules are decoupled from Spring's lifecycle.

Spring Framework provides two abstractions solving these exact two problems:

- **`TaskExecutor`**: submits a unit of work for execution; suited for on-demand asynchronous processing.
- **`TaskScheduler`**: registers an execution time or cadence; suited for one-shot, fixed-rate, fixed-delay, and cron tasks.

When declaring executors/schedulers as **Spring beans**, the container manages creation, dependency injection, initialization, destruction, and lifecycle coordination. Spring Boot 3.3 also auto-configures default executors/schedulers when appropriate. The `@Async` and `@Scheduled` annotations provide declarative usage.

After this lesson, you should be able to:

1. Distinguish **submitting work** from **work completion**, and **immediate execution** from **scheduled execution**.
2. Declare `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` as Spring beans with sensible bounds.
3. Use `TaskExecutor.execute`, `@Async`, `TaskScheduler.schedule`, `@Scheduled`, and `ScheduledFuture` with accurate semantics.
4. Understand `@EnableAsync`, `@EnableScheduling`, bean selection by name, and Spring AOP self-invocation.
5. Handle timeouts, cancellation, task rejection, asynchronous errors, and shutdown.
6. Run a Java 21 + Spring Boot 3.3.13 example, verify with JUnit, and explain why `ApplicationReadyEvent` does not automatically wait for background tasks.
7. Decide when an in-memory scheduler is sufficient and when a durable queue or distributed job scheduler is required.

## 2. Comparing TaskExecutor and TaskScheduler

| Criterion | `TaskExecutor` | `TaskScheduler` |
| --- | --- | --- |
| Purpose | Executes a submitted `Runnable` | Registers work to run at a time or cadence |
| Core API | `execute(Runnable)` | `schedule(Runnable, Instant)` |
| Result/handle | `AsyncTaskExecutor.submit(...)` returns `Future` | `ScheduledFuture<?>` for cancellation/tracking |
| Typical annotation | `@Async` | `@Scheduled` |
| Infrastructure enabler | `@EnableAsync` | `@EnableScheduling` |
| Common implementation | `ThreadPoolTaskExecutor` | `ThreadPoolTaskScheduler` |
| Risks | Full pool/queue, unobserved failures | Delayed jobs, overlapping load, wrong timezone scheduling |
| On context stop | Handles queued/running tasks per shutdown policy | Unregisters, cancels/drains tasks per lifecycle |

**Note:** `TaskExecutor` is not automatically a thread pool: this interface is an abstraction. An implementation may execute synchronously, spawn a thread per task, or use a pool. `TaskScheduler` likewise hides the underlying scheduling implementation.

### 2.1. Processing flow

```text
Service / Controller / ApplicationRunner
          |
          +-- executor.execute(runnable)
          |       |
          |       +-- queue / worker thread
          |              +-- run
          |              +-- succeed or fail
          |
          +-- scheduler.schedule(runnable, when)
                  |
                  +-- schedule target time
                  +-- when time arrives, worker runs
                  +-- complete or continue scheduling
```

Calling `execute` or `schedule` is **not** a signal that the business task has finished. With an asynchronous executor, the caller may proceed while the task is still sitting in the queue. With a scheduler, the task may not even have reached its scheduled time yet.

To **guarantee completion**, use `Future`/`CompletableFuture`, a latch, a callback, or durable job state. To **guarantee business ordering**, explicitly express that task B depends on task A rather than relying on thread names or incidental log order.

### 2.2. TaskExecutor and Java ExecutorService

Spring's `TaskExecutor` is similar to `java.util.concurrent.Executor` in its `execute(Runnable)` method, but integrates with Spring dependency injection, configuration, and lifecycle.

`AsyncTaskExecutor` supports task submission and returning handles. `ThreadPoolTaskExecutor` implements these contracts using a configurable thread pool.

Not every TaskExecutor provides `shutdown()`, `submit()`, or queue configuration; those belong to specific interfaces/implementations. When writing a service that only needs fire-and-forget execution, depend on the `TaskExecutor` interface. When a `Future` is needed, depend on `AsyncTaskExecutor` or a business abstraction returning a future.

## 3. Why let Spring manage it?

A common anti-pattern:

```java
@Service
class UnsafeNotificationService {
    private final ExecutorService pool = Executors.newFixedThreadPool(8);

    void submit(String id) {
        pool.submit(() -> send(id));
    }

    private void send(String id) {
        // A hypothetical I/O call.
    }
}
```

**This is an illustrative snippet, not a standalone program**: it lacks imports and any method to stop the pool. If the service fails to shut down the pool, the application may keep non-daemon threads alive after the context closes. If every service creates its own pool, tracking resources becomes even harder.

Better design:

```java
@Service
class NotificationService {
    private final TaskExecutor notificationExecutor;

    NotificationService(
            @Qualifier("notificationExecutor") TaskExecutor notificationExecutor) {
        this.notificationExecutor = notificationExecutor;
    }

    void submit(String id) {
        notificationExecutor.execute(() -> send(id));
    }

    private void send(String id) {
        // Business task.
    }
}
```

**This is a DI illustration**, requiring imports for `@Service`, `@Qualifier`, `TaskExecutor`, and a `notificationExecutor` bean definition. The shift: the component only submits work; pool configuration and shutdown live in one place.

Benefits:

- Spring manages initialization/destruction of the underlying executor implementation.
- Named, bounded pools are reused for matching workload classes.
- A different implementation can be injected in tests.
- Thread-name prefixes, metrics, rejection policies, and tracing can be configured centrally.
- Stopping new submissions and draining/canceling on context close can be coordinated at the application level.

**Limitation:** a Spring-managed pool is still **in-memory execution**. If the JVM crashes before a task finishes, Spring does not automatically persist the task to disk or replay it after restart. Critical business tasks require durable queues, transactions/outboxes, or job stores.

## 4. Spring Boot 3.3 auto-configuration

### 4.1. Default executor

In Spring Boot 3.3.13, if the context has no custom `Executor` bean, Boot can auto-configure an `AsyncTaskExecutor`. On Java 21:

- Without virtual threads enabled, it is typically `ThreadPoolTaskExecutor`.
- With `spring.threads.virtual.enabled=true`, it can be `SimpleAsyncTaskExecutor` using virtual threads.

In platform-thread mode, the auto-configured `ThreadPoolTaskExecutor` has 8 core threads by default in Boot 3.3; this can be adjusted via configuration:

```properties
spring.task.execution.thread-name-prefix=app-exec-
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=10s
```

These properties describe the **auto-configured executor**. They do not automatically configure custom beans created manually with `new ThreadPoolTaskExecutor()`.

When an application registers its own `Executor` bean, auto-configuration may back off. If using Spring MVC/WebFlux for asynchronous request processing, pay attention to `AsyncTaskExecutor` requirements and the **`applicationTaskExecutor`** bean name; avoid altering the default executor in ways that unintentionally affect integrations. When multiple executors exist, `@Async` without a qualifier may pick an unexpected bean; use `@Async("beanName")` or configure `AsyncConfigurer` explicitly.

### 4.2. Default scheduler

When scheduling infrastructure needs a scheduler (e.g., `@EnableScheduling`), Spring Boot can auto-configure:

- `ThreadPoolTaskScheduler` with one thread by default.
- `SimpleAsyncTaskScheduler` using virtual threads on Java 21 with `spring.threads.virtual.enabled=true`; in that case traditional scheduler pool-size properties do not apply the same way.

Example when using the pool-based auto-configured scheduler:

```properties
spring.task.scheduling.thread-name-prefix=sched-
spring.task.scheduling.pool.size=2
```

A single-threaded scheduler can cause other tasks to miss their schedule when one task runs long. However, increasing threads does not replace concurrency limits, overlap prevention, and downstream capacity control.

### 4.3. When should you define your own beans?

Use auto-configuration when needs are simple and configuring via properties is sufficient.

Create custom beans when you need to:

- Separate I/O and CPU task groups to avoid starvation.
- Use bounded pools/queues with dedicated backpressure policies.
- Use different schedulers for long vs. short tasks.
- Specify an explicit executor for `@Async("ioTaskExecutor")`.
- Specify an explicit scheduler for `@Scheduled(scheduler="taskScheduler")` in Spring Framework 6.1.
- Configure custom shutdown, metrics, task rejection, or thread-name prefixes.

**Rule:** custom `@Bean` brings custom configuration responsibility; do not expect Boot properties to automatically apply to it.

## 5. ThreadPoolTaskExecutor: pragmatic configuration

Sample configuration:

```java
@Bean("ioTaskExecutor")
ThreadPoolTaskExecutor ioTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("io-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
```

**Illustrative snippet inside a `@Configuration` class**, requiring proper imports; the full version is in section 7.

Meaning:

- **corePoolSize**: number of core workers.
- **maxPoolSize**: upper bound on workers.
- **queueCapacity**: limit on queued waiting tasks.
- **threadNamePrefix**: easy identification in logs/thread dumps.
- **waitForTasksToCompleteOnShutdown**: requests shutdown to wait for accepted tasks per implementation policy.
- **awaitTerminationSeconds**: configured termination wait timeout for the executor.

ThreadPoolExecutor typically grows up to core threads, then enqueues tasks, and only scales toward max once the queue is full. Therefore raising `maxPoolSize` alone while keeping an overly large queue **does not guarantee** more threads are actually created.

**Lifecycle warning:** `setWaitForTasksToCompleteOnShutdown(true)` must be designed alongside shutdown of beans that tasks depend on. The pool may keep running tasks while the context starts destroying data sources/HTTP clients. In production services, coordinate stopping intake, draining with a deadline, and keeping dependencies alive long enough (e.g., via `SmartLifecycle`), rather than treating one flag as a safe-shutdown guarantee.

### 5.1. Full queue and task rejection

If both the pool and queue exhaust capacity, `execute`/`submit` may throw `TaskRejectedException` depending on the Spring implementation.

Never swallow the exception and report the task as accepted. Options:

- Reject the request appropriately, advising retry with backoff.
- Send the job to a durable queue if loss is unacceptable.
- Drop in a controlled way if it is best-effort work, accompanied by a metric.
- For essential startup tasks, fail startup explicitly when the pool cannot accept work.

Avoid retrying infinitely on a request thread or spawning a new thread whenever the queue is full: that amplifies overload.

### 5.2. Choosing pool size by workload

- CPU-bound: concurrency generally should not far exceed CPU core count.
- I/O-bound: higher concurrency may help, but you must account for connection pools, timeouts, rate limits, and memory.
- Scheduler: long callbacks occupy scheduler threads, so consider separating job execution from scheduling.
- Tasks with deadlines: do not share a pool with indefinitely blocking tasks.

There is no universal `core=8, max=64` for every application. Choose based on load tests, metrics, and downstream capacity.

## 6. ThreadPoolTaskScheduler: configuration and contract

Sample configuration:

```java
@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("scheduled-");
    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setAwaitTerminationSeconds(10);
    return scheduler;
}
```

`ThreadPoolTaskScheduler` implements scheduling via `ScheduledExecutorService` and integrates with Spring's lifecycle. A bean named **`taskScheduler`** is the conventional name readily picked up by scheduling infrastructure. When multiple schedulers exist, specify which scheduler each job uses.

### 6.1. Basic TaskScheduler API

| API | Meaning |
| --- | --- |
| `schedule(Runnable, Instant)` | Schedules once at the specified instant |
| `schedule(Runnable, Trigger)` | Registers with a trigger, e.g., cron |
| `scheduleAtFixedRate(Runnable, Duration)` | Repeats at a fixed rate |
| `scheduleWithFixedDelay(Runnable, Duration)` | Repeats with a fixed delay |
| `ScheduledFuture.cancel(false)` | Requests canceling future runs without interrupting a running task |

`TaskScheduler` does not automatically create persistent jobs. Registrations live for the lifetime of the context/JVM. To survive deploys/restarts, persist job definitions in a durable store and re-register, or use Quartz/a dedicated job scheduler.

### 6.2. Fixed rate, fixed delay, and cron

**Fixed rate**: computes target execution times along a cadence from expected start times.

```java
@Scheduled(fixedRate = 10_000, initialDelay = 1_000)
public void refreshSnapshot() {
    // Lightweight periodic work.
}
```

**Fixed delay**: waits the full interval from when the previous run **finishes** until the next one starts.

```java
@Scheduled(fixedDelay = 10_000, initialDelay = 1_000)
public void pollRemoteService() {
    // May take a different duration each time.
}
```

**Cron**: runs on a time-of-day/calendar schedule.

```java
@Scheduled(
        cron = "0 0 9 * * MON-FRI",
        zone = "Asia/Ho_Chi_Minh")
public void sendWorkdayReport() {
    // 09:00 Monday to Friday in the selected timezone.
}
```

**The methods above are illustrative examples inside a Spring bean**, not part of the main project in section 7. `@EnableScheduling`, importing `org.springframework.scheduling.annotation.Scheduled`, and a scanned/registered bean are required.

Spring cron has **6 fields (including seconds)**. Do not copy 5-field cron templates verbatim from other tools. For local business schedules, specify the zone explicitly; if the zone observes DST, account for skipped or repeated times.

**Do not assume fixed rate always runs overlapping:** the actual scheduler, thread count, and trigger registration determine when an execution can start. A slow job can cause delays, backlogs, or unexpected run times; test your exact implementation.

### 6.3. Specifying a scheduler for @Scheduled in Spring 6.1

```java
@Scheduled(
        fixedDelay = 15_000,
        scheduler = "taskScheduler")
public void cleanup() {
    // ...
}
```

The `scheduler` attribute is available in Spring Framework 6.1 to explicitly specify a scheduler name/qualifier. When omitted and multiple scheduler beans exist, selection may be unintended or cause ambiguity. With multiple job groups, use an explicit qualifier.

## 7. Complete runnable example — Java 21 + Spring Boot 3.3.13

A **non-web** demo requiring no database or broker, illustrating an executor and scheduler that are both Spring beans. An `ApplicationRunner` invokes `@Async` on **another bean**, awaits `CompletableFuture` with a timeout, then schedules a one-shot task and awaits a `CountDownLatch`. Because it waits for completion, the program produces deterministic output.

### 7.1. Project structure

```text
managed-tasks-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/tasks/
    │   ├── ManagedTasksApplication.java
    │   ├── TaskConfiguration.java
    │   ├── ManagedWorker.java
    │   └── DemoRunner.java
    └── test/java/com/example/tasks/
        └── ManagedTasksIntegrationTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>managed-tasks-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

### 7.3. Application main

File `src/main/java/com/example/tasks/ManagedTasksApplication.java`:

```java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ManagedTasksApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManagedTasksApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner has already finished before SpringApplication.run returns.
        }
    }
}
```

`@SpringBootApplication` is placed in the root package to scan the classes. `WebApplicationType.NONE` prevents the app from opening an HTTP server. The context is closed via `try-with-resources` so Spring manages cleanup.

### 7.4. Configuring managed beans

File `src/main/java/com/example/tasks/TaskConfiguration.java`:

```java
package com.example.tasks;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableScheduling
public class TaskConfiguration {

    @Bean("ioTaskExecutor")
    public ThreadPoolTaskExecutor ioTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("io-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

Spring manages initialization/destruction of these two beans. You do not need to call `executor.initialize()` or `scheduler.initialize()` manually inside `@Bean` factory methods. `@EnableAsync` activates Spring AOP async support; `@EnableScheduling` activates processing of `@Scheduled` methods if any exist.

### 7.5. Worker using @Async and returning a result

File `src/main/java/com/example/tasks/ManagedWorker.java`:

```java
package com.example.tasks;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ManagedWorker {

    @Async("ioTaskExecutor")
    public CompletableFuture<String> normalize(String text) {
        String value = text.toUpperCase(Locale.ROOT);
        return CompletableFuture.completedFuture(value);
    }
}
```

Because the method is called **through the Spring bean proxy**, the computation runs on the `ioTaskExecutor` pool. Returning `CompletableFuture` lets the caller observe errors and completion. Inside a method already annotated with `@Async`, do not wrap work again in `CompletableFuture.supplyAsync` and accidentally hop to another executor.

### 7.6. Runner calling the executor and scheduler

File `src/main/java/com/example/tasks/DemoRunner.java`:

```java
package com.example.tasks;

import java.time.Instant;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;

@Component
public class DemoRunner implements ApplicationRunner {

    private final ManagedWorker worker;
    private final ThreadPoolTaskScheduler scheduler;

    public DemoRunner(
            ManagedWorker worker,
            @Qualifier("taskScheduler") ThreadPoolTaskScheduler scheduler) {
        this.worker = worker;
        this.scheduler = scheduler;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        System.out.println("RUNNER begin");

        CompletableFuture<String> work = worker.normalize("spring boot");
        String result = work.get(5, TimeUnit.SECONDS);
        System.out.println("ASYNC result=" + result);

        CountDownLatch completed = new CountDownLatch(1);
        ScheduledFuture<?> handle = scheduler.schedule(
                completed::countDown,
                Instant.now().plusMillis(100));

        if (handle == null) {
            throw new IllegalStateException("Scheduler rejected task");
        }
        if (!completed.await(5, TimeUnit.SECONDS)) {
            handle.cancel(false);
            throw new IllegalStateException("Scheduled task timed out");
        }

        System.out.println("SCHEDULE one-shot done");
        System.out.println("RUNNER done");
    }
}
```

Explanation:

1. Boot calls `ApplicationRunner.run` after context refresh.
2. The call from the runner to `ManagedWorker.normalize` goes through the Spring proxy so `@Async("ioTaskExecutor")` takes effect.
3. `work.get(5, TimeUnit.SECONDS)` waits for the async task to finish; if it fails or times out, the runner throws and startup does not proceed to the successful ready path.
4. `scheduler.schedule(Runnable, Instant)` registers a one-shot runnable.
5. `CountDownLatch` is decremented as soon as the runnable executes; the runner waits up to 5 seconds before printing completion.
6. Only after the runner returns normally does Boot proceed to `ApplicationReadyEvent`.

In the demo, the scheduled task only calls `countDown()`, so the latch accurately reflects completion. For real tasks, the signal must be emitted **after essential work completes**; if the task can throw an exception, provide an error channel back to the caller, such as `CompletableFuture`/`AtomicReference<Throwable>`, rather than blindly counting down in `finally` and treating all outcomes as success.

### 7.7. Build and run

Requires JDK 21, Maven, and dependency download access:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/managed-tasks-demo-0.0.1-SNAPSHOT.jar
```

The four lines **explicitly printed by the program** during the JAR run are:

```text
RUNNER begin
ASYNC result=SPRING BOOT
SCHEDULE one-shot done
RUNNER done
```

Logs, banners, and timestamps from Spring Boot may interleave; the block above is **not the entire stdout**.

Ordering is guaranteed via `Future.get` and `CountDownLatch.await`, not `Thread.sleep` or scheduler chance. If a runner only submits jobs without waiting, `ApplicationReadyEvent` may be published while those tasks are still unfinished.

### 7.8. Note on shutdown in the demo

After `SpringApplication.run` returns, `try-with-resources` closes the context. In a long-running web/worker application, the context normally stays open until receiving a shutdown signal, and pools remain available for new tasks. The demo closes immediately on purpose because both illustrative tasks were already awaited to completion.

## 8. The @Async annotation and self-invocation

### 8.1. Correct approach

```java
@Service
class ReportFacade {
    private final ManagedWorker worker;

    ReportFacade(ManagedWorker worker) {
        this.worker = worker;
    }

    CompletableFuture<String> start(String text) {
        return worker.normalize(text);
    }
}
```

This is a **supplementary pattern**, requiring imports if used standalone. `ReportFacade` and `ManagedWorker` are two separate Spring beans, so calls between them pass through the Spring-generated proxy for `@Async`.

### 8.2. Self-invocation makes @Async appear not to work

```java
@Service
class IncorrectService {

    public void submit() {
        this.processAsync(); // Internal call, may bypass proxy.
    }

    @Async("ioTaskExecutor")
    public void processAsync() {
        // ...
    }
}
```

This is an **illustrative anti-pattern**. Under default proxy mode, `this.processAsync()` within the same instance does not pass through the async proxy, so the method may run synchronously on the caller's thread. Fix this by moving the async method to another bean and injecting it; self-injection or `AopContext` is not recommended to patch an unclear design.

### 8.3. @Async void and results

- `@Async void`: the caller receives no future to observe success/failure. Errors can be routed to `AsyncUncaughtExceptionHandler`.
- `@Async CompletableFuture<T>`: suitable when waiting for results, composing workflows, or handling exceptions.
- `@Async` does not automatically propagate transactions across threads, retry tasks, or persist jobs across restarts.
- With multiple executors, use `@Async("beanName")` instead of relying on default selection.

## 9. TaskScheduler: one-shot, recurring, and cancellation

### 9.1. One-shot at an Instant

```java
ScheduledFuture<?> reminder = taskScheduler.schedule(
        () -> sendReminder(reminderId),
        Instant.now().plusSeconds(60));
```

This is an **illustrative snippet**, requiring a `TaskScheduler` bean, `reminderId` variable, and `sendReminder` method. For a one-shot schedule, `Instant` represents an absolute point in time; the task may run late if the scheduler is busy or the app is not yet running at that time.

### 9.2. Fixed rate/fixed delay programmatically

```java
ScheduledFuture<?> metrics = taskScheduler.scheduleAtFixedRate(
        this::reportMetrics,
        Duration.ofSeconds(30));

ScheduledFuture<?> polling = taskScheduler.scheduleWithFixedDelay(
        this::pollUpdates,
        Duration.ofSeconds(10));
```

This pattern belongs inside a bean with `reportMetrics` and `pollUpdates` methods and `Duration` imported. Keep the handle if you need to cancel from an orchestrating component or when configuration changes.

### 9.3. CronTrigger

```java
CronTrigger trigger = new CronTrigger(
        "0 0 9 * * MON-FRI",
        ZoneId.of("Asia/Ho_Chi_Minh"));

ScheduledFuture<?> handle =
        taskScheduler.schedule(this::sendDailyReport, trigger);
```

This is illustrative, requiring `CronTrigger`, `ZoneId`, and the target method. Use `CronTrigger` for dynamic schedule coordination; for static schedules, `@Scheduled(cron=...)` is usually simpler.

### 9.4. Cancel

```java
boolean cancellationRequested = handle.cancel(false);
```

`cancel(false)` requests stopping future runs without **interrupting** an already-running task. `cancel(true)` may request interruption, though it does not guarantee a task cooperates immediately. Do not treat cancel as an automatic rollback for DB writes or external side effects.

### 9.5. The scheduler does not guarantee exactly-once by itself

In a 3-replica cluster, every replica can register the same `@Scheduled` method, so the job can run **three times**. Local Spring scheduling does not elect a leader or share job state across nodes. If a job must run only once system-wide, use solutions such as distributed locks, Quartz with a configured job store, a broker/queue, or a dedicated scheduler service.

For critical tasks that must survive deploys/restarts, do not rely solely on holding a `ScheduledFuture` in memory.

## 10. Errors, timeouts, and concurrency

### 10.1. Execution exceptions

When calling `Future.get(5, TimeUnit.SECONDS)`, the caller may encounter:

| Situation | Outcome |
| --- | --- |
| Success | Future returns value |
| Task throws exception | `ExecutionException` wrapping cause |
| Wait timeout elapsed | `TimeoutException` |
| Caller thread interrupted | `InterruptedException` |
| Task was canceled | `CancellationException` |
| Pool/queue overloaded | Rejection may occur on submit |

If catching `InterruptedException` to continue handling, you typically need `Thread.currentThread().interrupt()` before exiting or propagating appropriately. Never use `catch(Exception ignored)` and silently treat the job as completed.

**Important:** timing out while waiting on a Future does not automatically stop the task; use cancellation/interruption and cooperative cancellation logic.

### 10.2. Scheduler error handling

A periodic job may throw errors; whether subsequent runs continue depends on the registration method and the scheduler's error handler. Manage logging, metrics, retries, and business job status. `ThreadPoolTaskScheduler` supports configuring an error handler; do not assume an exception in a recurring task is delivered back to a request thread.

### 10.3. Backpressure

With a pool of core=2, max=4, queue=32, many tasks blocking on I/O can fill the queue and cause rejections. Treat this as an overload signal. Increasing the pool endlessly does not fix the root cause: DB connection pools or external APIs may saturate even sooner.

A service can apply semaphores or rate limiters, bounded queues, appropriate 429/503 responses, and circuit breakers when load exceeds serving capacity.

### 10.4. ThreadLocal, transactions, and MDC

A `@Transactional` method dispatching `@Async` work to a pool **does not automatically carry the thread-local transaction along**. The task may read pre-commit data. `SecurityContext`, MDC correlation, request context, or custom ThreadLocals likewise do not propagate automatically.

Establish a new transaction boundary for the worker when needed; to run tasks only after commit, consider `@TransactionalEventListener(phase=AFTER_COMMIT)` or an outbox depending on durability requirements. For tracing, use proper context propagation/`TaskDecorator` rather than trying to copy transaction objects across threads.

## 11. Context lifecycle and shutdown

### 11.1. Spring-managed does not mean jobs survive a crash

When the context closes, Spring can invoke destroy/shutdown lifecycle hooks on managed `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` beans. However, `kill -9`, power loss, or JVM crashes can bypass shutdown hooks. There is no guarantee all queued/running tasks will finish.

### 11.2. Ordered shutdown

A desirable sequence:

```text
Stop signal received
  |
  +-- Stop accepting new work
  +-- Cancel/suspend recurring schedules as appropriate
  +-- Drain in-flight work within deadline
  +-- Save checkpoint or job status
  +-- Stop executor/scheduler
  +-- Close dependencies used by tasks
```

`setWaitForTasksToCompleteOnShutdown(true)` is insufficient if jobs still use a datasource or client closed by Spring during the same shutdown. For complex startup/shutdown, use `SmartLifecycle`, phases, and `stop(Runnable callback)` to coordinate draining with the dependency graph, making sure to invoke the callback once stopping truly completes.

### 11.3. Long scheduled tasks and a single-threaded pool

With the default single-threaded auto-configured scheduler, a 90-second scheduled job can delay other jobs. Solutions:

- Keep callbacks short and bounded with timeouts.
- Increase scheduler threads once load is measured and safe concurrency is known.
- Separate the scheduler from the executor running heavy I/O, with completion tracking.
- Use a persistent job scheduler if durable scheduling is needed.
- Monitor schedule lag and queues, not just execution counts.

### 11.4. Java 21 virtual threads

Configuration:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot 3.3 can switch **auto-configured** execution/scheduling to implementations using virtual threads. This does not automatically convert the custom `ThreadPoolTaskExecutor` in section 7 into a virtual-thread executor. Virtual threads help with many I/O-waiting tasks but do not add CPU cores or DB capacity, so you must still bound concurrency and protect downstream systems.

With `SimpleAsyncTaskScheduler` using virtual threads, fixed-delay has notable scheduling semantics; fixed-rate/cron jobs generally fit better in the virtual-thread-aligned model. Spring Framework 6.1 documentation explains these cases in detail.

## 12. Testing with Spring Boot Test and JUnit

### 12.1. Do not use sleep to prove completion

`Thread.sleep(100)` in tests does not guarantee a task ran: slow CI machines or GC pauses can cause flaky failures. Use `Future.get(timeout)`, `CountDownLatch.await(timeout)`, or a fake scheduler/clock.

### 12.2. Integration test

File `src/test/java/com/example/tasks/ManagedTasksIntegrationTest.java`:

```java
package com.example.tasks;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ManagedTasksApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ManagedTasksIntegrationTest {

    @Autowired
    private ManagedWorker worker;

    @Autowired
    @Qualifier("taskScheduler")
    private ThreadPoolTaskScheduler scheduler;

    @Test
    void processesAsyncAndScheduledTasks() throws Exception {
        assertEquals("HELLO",
                worker.normalize("hello").get(5, TimeUnit.SECONDS));

        CountDownLatch finished = new CountDownLatch(1);
        ScheduledFuture<?> handle = scheduler.schedule(
                finished::countDown,
                Instant.now().plusMillis(50));

        assertNotNull(handle);
        assertTrue(finished.await(5, TimeUnit.SECONDS));
    }
}
```

`@SpringBootTest` starts a real context, allowing verification of executor/scheduler wiring. This test may trigger `DemoRunner` during Spring Boot startup because it is an `ApplicationRunner` bean; runner lines in test logs do not mean the test ran twice.

When using another scheduler or modifying thread pool settings, keep finite timeouts. If a test schedules multiple tasks and may fail, use `try/finally` to cancel handles and avoid leaking scheduled registrations.

### 12.3. Faster unit tests

Not every test needs a Boot context. If a business service only depends on `TaskExecutor`, you can inject a fake executor running `runnable.run()` directly to unit-test logic; however, that test **does not prove** thread pool configuration works. Use integration tests for Spring wiring and latch-based tests for critical concurrency.

## 13. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `@Async` does not run in background | Missing `@EnableAsync`, self-invocation, or unmanaged bean | Enable async infrastructure, call through Spring proxy |
| `@Scheduled` does not run | Missing `@EnableScheduling`, unscanned bean, closed context | Verify registration and scheduling |
| Boot auto-configured pool missing | Custom `Executor` caused auto-config to back off | Distinguish auto-config from named custom beans |
| Thread pool never scales to max | Queue still has space, threshold not reached | Review core/queue/max semantics |
| `@Async` picks the wrong executor | Multiple beans of same type, unclear qualifier | `@Async("ioTaskExecutor")` |
| Cron runs at the wrong time | Wrong 6-field cron or timezone | Specify zone explicitly and test schedule |
| Multiple replicas run the same job | In-memory scheduling per JVM | Distributed lock/persistent scheduler |
| Scheduler runs slowly | Blocking job occupies scheduler thread | Scale pool thoughtfully or offload execution |
| App reports ready while tasks are unfinished | Runner submits and returns | Wait for completion with timeout if essential |
| Tasks lost on app restart | Only queued in memory | Durable queue, outbox, job persistence |
| `@Async void` error unseen by caller | No Future | AsyncUncaughtExceptionHandler/monitoring |
| Shutdown hangs or tasks hit closed resources | Drain/shutdown phases uncoordinated | `SmartLifecycle`, timeouts, dependency ordering |
| Task does not see active transaction | Offloaded to another thread | New transaction boundary/AFTER_COMMIT/outbox |
| Tests using `Thread.sleep` flake | No completion signal | Latches/futures/fake clock |
| `@Scheduled` callback takes request args | Framework calls method on schedule, not per request | Use injected dependencies or programmatic scheduling |

### 13.1. Diagnostic checklist

1. Are the executor/scheduler properly registered as Spring beans?
2. Are `@EnableAsync` and `@EnableScheduling` active?
3. Does the `@Async` call go through a Spring proxy?
4. Which named executor/scheduler bean is actually being used?
5. Was the task submitted, started, or completed? Is there a Future/ack?
6. Is there pool/queue saturation or task rejection?
7. Does `@Scheduled` use fixedRate, fixedDelay, or cron, and which timezone?
8. Does the job run longer than its interval, or run on multiple instances concurrently?
9. Are exceptions being ignored on background threads?
10. Is there reliance on the request thread's ThreadLocal/transaction?
11. During shutdown, do you stop accepting new jobs before closing dependencies?
12. If the JVM dies, must the task recover from durable state?

## 14. Applicability scenarios

**Best-effort email sending:** an `@Async("ioTaskExecutor")` method fits if losing occasional notifications causes no data inconsistency, though timeouts, errors, and metrics are still needed. If email must reliably send after commit, use an outbox/queue.

**Short computations:** a `TaskExecutor` with concurrency bounded to CPU suits CPU-bound work; avoid spawning too many threads for CPU-bound computation.

**Periodic cache refresh:** `@Scheduled(fixedDelay=...)` or programmatic scheduling fits when per-replica refresh is valid. If only one writer is allowed in a cluster, add coordination.

**In-JVM reminder scheduling:** `TaskScheduler.schedule` is convenient for a one-shot without persistence requirements. If users expect reminders to survive deploys/restarts, use a job store or durable scheduler.

**Startup data verification:** `ApplicationRunner` can submit work to a Spring-managed executor and **await the Future** successfully before Boot publishes `ApplicationReadyEvent`. If the task fails, propagate the exception so startup fails instead of falsely reporting ready.

**Message-processing applications:** a task executor is merely where workers run; acknowledgment, retry, idempotency, deduplication, ordering by business key, and consumer shutdown still require dedicated design.

## 15. Exercises and self-check questions

1. Compare `TaskExecutor.execute(Runnable)` with `TaskScheduler.schedule(Runnable, Instant)`.
2. Why is creating `new Thread(...)` in every service hard to manage over the lifecycle?
3. Explain the difference between submitting a task and task completion.
4. Write two beans `ioTaskExecutor` and `cpuTaskExecutor`, targeting each via `@Async`.
5. Why might `this.processAsync()` in the same bean fail to run in the background?
6. In the Maven example, why does `ASYNC result` appear before `RUNNER done`?
7. If you remove `completed.await(...)` in the runner, does `ApplicationReadyEvent` guarantee the scheduled task ran?
8. When `queueCapacity` is large, why might `maxPoolSize` rarely be used?
9. With core=1, max=2, queue=1 and four concurrent tasks, how might the last task be rejected?
10. When should you use fixedRate vs. fixedDelay?
11. Write a cron expression for 09:00 on weekdays in `Asia/Ho_Chi_Minh`.
12. How do you cancel a `ScheduledFuture` registration when a schedule changes?
13. Why does an overly long periodic task on a single-threaded scheduler delay other jobs?
14. Why is `@Async void` unsuitable when the caller needs the business outcome?
15. Describe using `CompletableFuture` and a timeout to coordinate a startup task.
16. Why does another thread not automatically see the publisher's thread-local transaction?
17. When should you use `@TransactionalEventListener(AFTER_COMMIT)` vs. an outbox?
18. Why does a Spring-managed pool not mean tasks are durably persisted across JVM crashes?
19. If 3 pods all have `@Scheduled`, how many times can the job run at the same scheduled tick?
20. Propose a way to test scheduling without `Thread.sleep`.
21. Why must shutdown dependencies be considered before enabling `waitForTasksToCompleteOnShutdown`?
22. With Java 21 virtual threads, how can auto-configured executors change?
23. A system processes 1000 tasks/sec while the DB only handles 100 transactions/sec: will increasing pool size fundamentally solve it?
24. Design a `QUEUED → RUNNING → DONE/FAILED` pipeline with deadlines, retries, backpressure, and durable storage for non-droppable jobs.

**Success criteria:** configure Spring-managed executors and schedulers properly, run the Java 21/Spring Boot 3.3 demo, understand completion/timeouts, apply the right scheduling API, and design with control over errors, shutdown, transactions, and scale.

## 16. Official references

- Spring Boot 3.3.13 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 — TaskExecutor API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework 6.1 — TaskScheduler API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework 6.1 — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 — ThreadPoolTaskScheduler: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
- Spring Framework 6.1 — EnableAsync: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework 6.1 — Scheduled: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
