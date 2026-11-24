# Avoiding Unmanaged Executors Without Lifecycle Cleanup in Spring Boot

## 1. The problem: an executor can be created, but who will close it?

A Spring Boot application often has many tasks that do not run directly on request threads: sending notifications, processing files, calling partner APIs, executing `@Async`, `@Scheduled` jobs, message broker consumers, or background batches. Those tasks require an execution facility such as `Executor`, `ExecutorService`, `TaskExecutor`, or `TaskScheduler`.

A common mistake is **creating a thread pool without defining who is responsible for stopping it**:

```java
// ANTI-PATTERN: business method creates a new pool without closing it.
public void handleRequest() {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    pool.submit(() -> doWork());
}
```

This is an illustrative snippet; `doWork()` is not defined. If every request calls this method, each call creates a separate pool. Default threads from `Executors.newFixedThreadPool` are non-daemon; once the pool creates workers, threads typically remain alive waiting for the next task. **Failing to call `shutdown()` can retain threads and resources indefinitely**, even preventing the JVM from exiting as expected.

An even riskier scenario: a background task holds a database connection, HTTP client, file handle, or another bean's resource. While `ApplicationContext` is closing, an unmanaged executor can keep running tasks after those resources have been destroyed.

**Central principle:** every executor must have an **owner**, an initialization lifecycle, an intake policy, a policy for canceling/completing running tasks, a shutdown timeout, and error handling. In Spring Boot, prefer **Spring-managed executors**; if you must construct one directly from the JDK, shut it down with discipline.

This lesson uses **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x**. Examples include a standalone Java program and a complete hands-on Spring Boot application.

## 2. What does "reclaiming an executor" involve?

Closing an executor is more than calling a method named `close`. You must manage its entire lifecycle:

1. **Creation:** who builds the pool, thread factory, max threads, and queue?
2. **Ownership:** does the pool belong to a request, a Spring bean, or a process?
3. **Submission:** which services may submit and when must submission stop?
4. **Load pressure:** is the queue bounded, with an explicit rejection policy?
5. **Intake stop:** during shutdown, block new work from entering the pool.
6. **Completion/cancellation:** how long are running tasks given, and how are queued tasks handled?
7. **Release:** do threads terminate, and are resources inside tasks closed?
8. **Observability:** are there metrics for active threads, queue depth, rejected tasks, and shutdown timeouts?

A pool may **not leak heap objects** yet still cause major trouble by retaining threads, thread-locals, classloader references, connections, or open I/O. In web apps redeployed inside the same JVM or tests creating multiple `ApplicationContext` instances, unclosed pools can pin old classloaders, hinder GC, and run tasks outside their intended lifecycle.

### 2.1. Do not confuse pool reuse with a pool leak

**Pool reuse** is desirable: one executor is intentionally created for a defined scope, shared across many tasks, and eventually closed.

**A leak** occurs when a pool is no longer useful or has lost its managing owner yet stays alive holding resources. A singleton pool living for the lifetime of the application is not a leak; that pool becomes a problem if `ApplicationContext.close()` ran while it keeps running.

## 3. Java APIs to distinguish

Java provides `Executor` and `ExecutorService`:

- `Executor.execute(Runnable)`: submits a unit of work; the `Executor` interface itself **has no shutdown contract**.
- `ExecutorService.submit(...)`: submits a task and returns a `Future` to observe result/exception/cancellation.
- `ExecutorService.shutdown()`: **stops accepting new tasks**, gives submitted tasks a chance to complete, and then terminates the pool. This call **does not wait** for tasks to finish.
- `ExecutorService.shutdownNow()`: attempts to stop running tasks (typically via `interrupt`), does not start queued waiting tasks, and returns a list of unstarted tasks. This is **best effort**, with no guarantee every task stops immediately.
- `ExecutorService.awaitTermination(timeout, unit)`: **waits with a bound** until the pool terminates after shutdown, returning `true` if terminated or `false` if the timeout elapsed.
- `isShutdown()`: has shutdown been requested? Does not mean all tasks finished.
- `isTerminated()`: after shutdown, have all tasks ended and is the pool no longer running work?
- `Future.cancel(true)`: requests canceling the corresponding task, potentially interrupting if running; does not guarantee task cooperation.

### 3.1. State table

| Situation | `isShutdown()` | `isTerminated()` | Meaning |
| --- | --- | --- | --- |
| Pool accepting work | `false` | `false` | Submissions allowed. |
| Just called `shutdown()`, tasks still running | `true` | `false` | Rejects new tasks, still finishing old tasks. |
| Called `shutdownNow()` yet tasks refuse to stop | `true` | `false` | Cannot assume all tasks stopped. |
| Pool completed shutdown | `true` | `true` | Old tasks ended and pool terminated. |

**Java 17 note:** `ExecutorService` does **not yet** implement `AutoCloseable.close()` in Java 17's contract so you cannot write `try (ExecutorService pool = ...)` by default. Use `try/finally` and explicitly call `shutdown`/`awaitTermination`; do not copy examples from newer JDK versions into a Java 17-locked project without checking.

### 3.2. Interruption is a cooperative contract

`shutdownNow()` may invoke `Thread.interrupt()` on workers. If a task:

- Is blocked in `Thread.sleep`, `BlockingQueue.take`, or interrupt-supporting APIs, it can throw `InterruptedException`.
- Is executing an I/O library that does not properly support interruption, it may **keep running**.
- Has an infinite loop ignoring the interrupt flag, the pool may **never terminate**.

Therefore "calling shutdownNow and assuming it stopped" is a false conclusion. Tasks must be written to react to cancellation, enforce their own timeouts, and release resources in `finally`/try-with-resources.

## 4. First anti-pattern: creating a pool per request

Example to avoid:

```java
@RestController
class ExportController {

    @PostMapping("/exports")
    String startExport() {
        ExecutorService pool = Executors.newCachedThreadPool();
        pool.submit(() -> createExport());
        return "accepted";
    }
}
```

This is a **counter-example**, lacking `createExport()` and imports. `newCachedThreadPool` can expand workers with incoming tasks; creating **a pool per request** causes unbounded thread/resource growth. Returning a response does not mean the task finished or has anywhere storing its state.

**Fix:** create **one executor managed with the application's lifecycle**, inject it into services, and reuse it across requests; if work must survive process restarts, use an appropriate durable queue/job store rather than only an in-memory thread pool.

Never put `Executors.newFixedThreadPool(...)`, `newScheduledThreadPool(...)`, or `newSingleThreadExecutor()` inside a controller/service method just to "quickly run in the background".

## 5. Second anti-pattern: self-created executor field in a bean without destroy

```java
@Service
class ReportService {

    private final ExecutorService pool =
            Executors.newFixedThreadPool(4);

    public void submitReport(Runnable task) {
        pool.submit(task);
    }
}
```

The class above is also **unsafe** without a destroy callback. A Spring-managed `@Service` bean **does not mean every manually instantiated ExecutorService in a field is automatically shut down by Spring**. Spring manages the ReportService bean, yet the pool object you created sits inside it; cleanup requires an explicit contract.

Two appropriate options:

1. Extract the executor into **its own bean**, letting Spring manage the executor's lifecycle directly.
2. If the pool must stay private, give the owning bean a `@PreDestroy`/`DisposableBean`/destroy method that shuts down and waits within bounds.

Never put cleanup in `finalize()` or rely on GC: garbage collection is not a guaranteed thread pool shutdown mechanism. Live threads can even hold references preventing GC of the object.

## 6. Time-bounded shutdown procedure

Conceptually recommended JDK pattern:

```text
1. Stop submitting new tasks.
2. executor.shutdown(): reject new tasks, allow submitted tasks to run.
3. awaitTermination(timeout): wait within bounds.
4. If timed out:
       executor.shutdownNow(): attempt to interrupt running tasks,
                              return list of unstarted tasks.
5. Optionally awaitTermination again briefly.
6. If still running: log the failure explicitly, do not claim clean shutdown.
7. If the waiting thread is interrupted:
       call shutdownNow, restore interrupted flag.
```

Choosing the timeout is a business policy, not a JDK constant. A 20 ms memory-read task differs from a 10-second file-writing job or a message consumer needing to commit offsets.

### 6.1. Two-phase shutdown does not guarantee zero data loss

`shutdown()` awaits submitted work if tasks cooperate and have time. When a timeout leads to `shutdownNow()`:

- Waiting tasks may **never have executed**.
- Running tasks may be interrupted mid-operation.
- A `Future` may be canceled or fail.
- A task that partially wrote external data may leave intermediate state.

If losing tasks is unacceptable, design **persistent queues, checkpoints, idempotency keys, transactions, or controlled retries**. An in-memory `ExecutorService` does not provide exactly-once delivery.

### 6.2. Do not wait indefinitely in a shutdown hook

Calling `awaitTermination(Long.MAX_VALUE, ...)` can keep the process from exiting due to one stuck task or unresponsive dependency. In Kubernetes/containers, `terminationGracePeriodSeconds` can cut the process off before cleanup finishes. Choose finite timeouts and monitor expirations.

## 7. Complete Java 17 example: a pool with owner and cleanup

The following example **does not require Spring**. It uses `ThreadPoolExecutor` with a bounded queue, accepts a task, retrieves the result via `Future`, and performs a time-bounded shutdown inside `finally`.

**File:** `ExecutorShutdownDemo.java`

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ExecutorShutdownDemo {

    private static final AtomicInteger NEXT_ID = new AtomicInteger();

    public static void main(String[] args) throws Exception {
        ThreadFactory factory = task -> {
            Thread thread = new Thread(
                    task, "lesson-worker-" + NEXT_ID.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,
                2,
                10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(4),
                factory,
                new ThreadPoolExecutor.AbortPolicy());

        try {
            Future<String> answer =
                    pool.submit(() -> "processed:42");

            System.out.println("RESULT "
                    + answer.get(5, TimeUnit.SECONDS));
        } finally {
            shutdownAndAwait(pool);
        }

        System.out.println("TERMINATED " + pool.isTerminated());
    }

    private static void shutdownAndAwait(ExecutorService pool) {
        pool.shutdown(); // Reject new tasks, give existing tasks a chance to finish.

        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                List<Runnable> neverStarted = pool.shutdownNow();
                System.err.println(
                        "NOT_STARTED " + neverStarted.size());

                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("POOL_STILL_RUNNING");
                }
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

### 7.1. Compile and run commands

With JDK 17+ in the directory containing the file:

```bash
javac -encoding UTF-8 ExecutorShutdownDemo.java
java ExecutorShutdownDemo
```

Stdout on a normal successful run:

```text
RESULT processed:42
TERMINATED true
```

The sample task is very short and finishes before shutdown. Therefore `NOT_STARTED` does not appear under normal conditions.

### 7.2. Why this example is reliable

- `ThreadPoolExecutor` is created **once** and held in a variable with clear ownership.
- `ArrayBlockingQueue<>(4)` bounds waiting tasks in the queue.
- `AbortPolicy` rejects new tasks when the executor has stopped or has no space left.
- `Future.get(5, TimeUnit.SECONDS)` waits for the result with a timeout rather than forever.
- `finally` guarantees cleanup even if result handling throws after creating the pool.
- `shutdown()` stops accepting new tasks.
- `awaitTermination` bounds the waiting duration.
- `shutdownNow()` serves strictly as best-effort escalation if the timeout expires.
- `Thread.currentThread().interrupt()` restores the interrupt flag if the waiting thread is interrupted while stopping.

**There is no guarantee** that a task deliberately ignoring interrupts will stop. If `POOL_STILL_RUNNING` appears, that is an error condition to diagnose, not a "cleanup succeeded" state.

### 7.3. Why intentionally setDaemon(false)?

To make clear that non-daemon threads can keep the JVM alive if the pool is not shut down. Yet marking threads as daemon is **not a fix for leaks**: daemon threads can be terminated abruptly by the JVM with no guarantee of flushing/committing work. The right fix is lifecycle management and coordinated shutdown.

### 7.4. Java 17 and try-with-resources

Notice the example does **not** write `try (ExecutorService pool = ...)`. Java 17-targeted code uses `try/finally` because `ExecutorService` in JDK 17 does not provide `close()` as an `AutoCloseable`. When reading newer Java documentation, always cross-check APIs against the exact version in use.

## 8. Making the executor a Spring-lifecycle-managed bean

For Spring Boot applications, the most common way to reduce risk is declaring `ThreadPoolTaskExecutor` as a **Spring-managed singleton bean**. This class lives in:

```java
org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
```

It implements Spring execution/lifecycle contracts and includes shutdown logic via `ExecutorConfigurationSupport`. When the context closes per standard contract, Spring invokes the appropriate destroy/lifecycle callbacks on the executor bean.

A recommended configuration:

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("businessExecutor")
    ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("business-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
```

The snippet above is an **illustrative class inside the project package**, requiring imports for `@Configuration`, `@EnableAsync`, `@Bean`, `ThreadPoolTaskExecutor`, and JDK `ThreadPoolExecutor`. The complete example in section 10 provides full imports and runnable files.

**Important:** When `ThreadPoolTaskExecutor` is declared via `@Bean`, the Spring container invokes the related init/destroy callbacks. Do not call `initialize()` manually inside the `@Bean` method and let the container initialize it a second time. Nor do you need to add `@PreDestroy` to the executor bean itself to invoke shutdown twice.

### 8.1. Meaning of the two shutdown flags

In Spring Framework 6.1:

- `setWaitForTasksToCompleteOnShutdown(true)`: asks the executor to process already-queued tasks rather than actively interrupting/discarding them immediately at shutdown. It can **bypass the coordinated lifecycle stop phase** to wait during its own shutdown step; do not treat this as a free option.
- `setAwaitTerminationSeconds(10)`: allows the destroy/shutdown operation to wait up to 10 seconds before continuing container shutdown. The goal is to keep other beans/resources alive during that required window.
- When the wait expires, shutdown proceeds; **there is no guarantee all tasks finished**. If tasks ignore interrupts or the backlog is huge, tasks may still run past the deadline.
- These settings belong to the configured **executor instance** and do not automatically alter other `ExecutorService` instances created elsewhere.

If you enable `waitForTasksToCompleteOnShutdown(true)`, watch queue depth and task durations: a huge queue can require minutes in total, exceeding your shutdown timeout.

### 8.2. A bounded queue matters as much as cleanup

A `ThreadPoolTaskExecutor` with an unbounded queue can accumulate infinite backlog. While the queue is not full, worker count typically stays at core pool size, so setting a large `maxPoolSize` **does not automatically scale the pool** with an unbounded queue.

Setting a finite `queueCapacity` and sensible `maxPoolSize` controls resources. Yet you also need a **rejection policy**: return an error/throttle response, retry later, or route to a durable queue; never drop tasks silently.

`CallerRunsPolicy` can run tasks on the submitting thread when saturated, creating **backpressure**, though on HTTP request threads it can spike latency; during shutdown this policy also behaves differently. Never enable it without understanding real load and response requirements.

## 9. Spring Boot 3.3 auto-configured TaskExecutor and TaskScheduler

In a Java 17 app with standard configuration, Spring Boot 3.3 can auto-configure an `AsyncTaskExecutor`, defaulting to `ThreadPoolTaskExecutor` when no `Executor` bean causes auto-configuration to back off.

In certain integrations, the auto-configured executor also serves:

- `@EnableAsync` and `@Async`.
- Spring MVC asynchronous request handling.
- Certain GraphQL/WebFlux integrations depending on executor type and bean name conditions.

**Bean name and type matter.** With a custom `Executor`, auto-configuration may back off; Spring MVC/WebFlux also have specific conditions for picking a bean named `applicationTaskExecutor` of a compatible type. Never define an arbitrary executor and assume every async mechanism in the app automatically uses that pool.

For `@Scheduled`, Spring Boot can auto-configure a `TaskScheduler`, typically `ThreadPoolTaskScheduler` on Java 17 without virtual threads; the default scheduler usually has one thread, tunable via `spring.task.scheduling` properties.

### 9.1. Configuring the Boot auto-configured executor

**Applies only when using the matching auto-configuration path; does not automatically affect custom beans.**

```properties
# Task-processing pool, e.g. when Boot creates ThreadPoolTaskExecutor.
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
spring.task.execution.thread-name-prefix=app-task-

# Allow waiting for accepted tasks when stopping.
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=15s

# Scheduler if auto-configured by Boot.
spring.task.scheduling.pool.size=2
spring.task.scheduling.thread-name-prefix=app-schedule-
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=10s
```

This is an `application.properties` snippet; these keys are documented in Spring Boot 3.3 common application properties. Inspect which executor is actually created at runtime, especially when the app or a starter declares custom beans.

### 9.2. Do not confuse Boot properties with manually calling Executors.newFixedThreadPool

If a service directly calls:

```java
ExecutorService unmanaged = Executors.newFixedThreadPool(4);
```

then `spring.task.execution.shutdown.*` properties **do not magically inject themselves into this object**. It is a JDK object outside Spring's ownership unless you register it as a bean or wrap it with cleanup.

### 9.3. Java 21 virtual threads

Spring Boot 3.3 can use virtual threads on Java 21+ with `spring.threads.virtual.enabled=true`. Auto-configured executors/schedulers can then use implementations different from traditional thread pools; many pool properties cease to apply.

Even though virtual threads are lighter, that **does not mean ownership, cancellation, timeouts, and task lifecycles can be ignored**. Never treat Java 21 examples as runnable on Java 17; this lesson keeps all primary examples Java 17-compatible.

## 10. Runnable Spring Boot 3.3 example: @Async using a managed pool

This complete example has three Java files and one build script. It:

- Creates a `ThreadPoolTaskExecutor` as a Spring bean named `businessExecutor`.
- Uses `@Async("businessExecutor")` to dispatch tasks to that specific pool.
- Uses a runner that receives a `CompletableFuture` and awaits the result within bounds.
- Closes `ApplicationContext` when the non-web program exits so the container actively cleans up the executor.
- Never creates an `ExecutorService` per request.

### 10.1. Structure

```text
managed-async-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/pool/
    ManagedAsyncApplication.java
    AsyncConfiguration.java
    ReportWorker.java
```

### 10.2. settings.gradle

```groovy
rootProject.name = 'managed-async-demo'
```

### 10.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This is the build script for Java 17+/Boot 3.3.x. With a Gradle Wrapper and valid JDK, run via `bootRun`. `spring-boot-starter-web` is not needed because the focus is pool lifecycle, not HTTP.

### 10.4. ManagedAsyncApplication.java

```java
package com.example.pool;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManagedAsyncApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManagedAsyncApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("CONTEXT_READY");
        }

        System.out.println("CONTEXT_CLOSED");
    }

    @Bean
    ApplicationRunner runExample(ReportWorker worker) {
        return args -> {
            String value = worker.generate("42")
                    .get(5, TimeUnit.SECONDS);
            System.out.println("ASYNC_RESULT " + value);
        };
    }
}
```

### 10.5. AsyncConfiguration.java

```java
package com.example.pool;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("businessExecutor")
    ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("business-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
```

### 10.6. ReportWorker.java

```java
package com.example.pool;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {

    @Async("businessExecutor")
    public CompletableFuture<String> generate(String id) {
        return CompletableFuture.completedFuture("report:" + id);
    }
}
```

**Explanation:**

- `@EnableAsync` enables `@Async` processing under standard proxy semantics.
- `@Async("businessExecutor")` targets the exact Spring-managed pool.
- `ReportWorker` is a separate bean from the caller of `generate(...)`, so the call passes through Spring's proxy. Calling `this.generate(...)` inside the same class can **bypass the proxy**, running synchronously; avoid self-invocation when async execution is expected.
- `CompletableFuture<String>` lets callers observe results and exceptions instead of blind fire-and-forget.
- The runner calls `get(5, TimeUnit.SECONDS)` so it does not wait forever.
- `ThreadPoolTaskExecutor` is initialized/destroyed by Spring per bean lifecycle; never call `shutdown()` manually in a controller or inside every `generate(...)`.
- `try-with-resources` here applies to **ConfigurableApplicationContext**, which is `AutoCloseable`; not a Java 17 `ExecutorService`.

### 10.7. Run and stdout

From the directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`; PowerShell: `.\gradlew.bat bootRun`.

Ignoring banners/framework logs, when the task succeeds, three lines **printed by the program itself** appear in order:

```text
ASYNC_RESULT report:42
CONTEXT_READY
CONTEXT_CLOSED
```

In this non-web example, after `SpringApplication.run(...)` returns, the `try` block exits and closes the context. If the executor bean must wait for unfinished tasks, Spring applies the configured shutdown policy. Because the demo task already completed via `Future.get(...)`, shutdown is normally fast.

**Limitation:** This is a pedagogical example, not measuring real throughput or guaranteeing exact thread start/stop timing. A startup failure or timeout breaks the success path above; that is why failure policies must be managed.

## 11. When using a JDK ExecutorService as a Spring bean

Not every pool must be a `ThreadPoolTaskExecutor`. A legacy library may require an `ExecutorService`. You can register a bean with a destroy callback:

```java
@Configuration(proxyBeanMethods = false)
class LegacyExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService legacyExecutor() {
        return Executors.newFixedThreadPool(2);
    }
}
```

This is an **illustrative class snippet**, requiring imports for `ExecutorService`, `Executors`, `Configuration`, and `Bean`.

**Key boundary:** `destroyMethod = "shutdown"` only calls `shutdown()` when the bean is destroyed. In Java 17, `shutdown()` **does not wait for tasks to finish**. If bounded waiting and cancellation policies are needed, build an **owner bean** with a `@PreDestroy`/`DisposableBean.destroy()` method calling full `shutdownAndAwaitTermination`, rather than assuming a destroy method name suffices.

### 11.1. Owner bean with @PreDestroy

```java
package com.example.pool;

import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class OwnedWorkerPool {

    private final ExecutorService delegate = new ThreadPoolExecutor(
            2, 4, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(32),
            new ThreadPoolExecutor.AbortPolicy());

    public void submit(Runnable task) {
        delegate.execute(task);
    }

    @PreDestroy
    public void stop() {
        delegate.shutdown();

        try {
            if (!delegate.awaitTermination(10, TimeUnit.SECONDS)) {
                List<Runnable> notStarted = delegate.shutdownNow();
                System.err.println(
                        "Unstarted tasks: " + notStarted.size());

                if (!delegate.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println(
                            "Worker pool did not terminate in time");
                }
            }
        } catch (InterruptedException ex) {
            delegate.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

This is a **complete Java file** inside a Spring Boot 3.3 project with `spring-boot-starter` and component scanning covering its package. It illustrates a bean **owning** a private pool where Spring invokes `@PreDestroy` on bean destruction.

Do not simultaneously register `delegate` itself as an independent bean with another destroy method; if two owners shut down the same pool, double cleanup and unpredictable shutdown order can occur. Only one primary owner should govern the teardown policy.

### 11.2. @PreDestroy alone does not guarantee tasks finished

In the callback, clarify:

- Are new incoming tasks blocked?
- Do you wait for old tasks, and for how long at most?
- On timeout, how are tasks canceled and logged?
- Do tasks respond to `interrupt`?
- Must unstarted tasks be retried/persisted?
- Do resource beans used by tasks remain alive during the wait?

If you only call `delegate.shutdown()` and return, the container may keep destroying database or HTTP clients while tasks still run. Therefore in systems with critical dependencies, bounded waiting and resource-closing order must be designed explicitly.

## 12. @Scheduled and schedulers also have a lifecycle

An application using `@EnableScheduling` and `@Scheduled` may need a `TaskScheduler` to run periodic tasks. The scheduler **also owns threads and queues**, carrying the same shutdown responsibility.

A bean can be configured as:

```java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
class SchedulingConfiguration {

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

This is an illustrative class snippet, requiring imports for `Configuration`, `EnableScheduling`, `Bean`, and `ThreadPoolTaskScheduler`. When Spring-managed, the scheduler has a matching shutdown lifecycle. When using the Boot auto-configured scheduler, set `spring.task.scheduling.shutdown.await-termination` and `...period` instead of manually creating a pool.

### 12.1. Scheduled tasks can prolong shutdown

A 10-minute periodic task may be running when the container receives SIGTERM. Decide the policy:

- Wait up to a bounded duration for the task to finish?
- Interrupt the task after timeout?
- Accept stopping a job and retrying on the next scheduled tick?
- Use distributed locks/leases to prevent two instances from running one job during a rollout?
- Record checkpoints to resume if a job stops mid-way?

Executor shutdown **does not automatically provide** exactly-once semantics, distributed coordination, or transaction rollbacks. For critical financial/data jobs, use durable job processing mechanisms.

## 13. Stop ordering: readiness, work sources, executors, and resources

Shutdown design usually requires more than "waiting on a thread pool".

```text
SIGTERM / instance stop request
       |
       v
Readiness REFUSING_TRAFFIC / drain new traffic
       |
       v
Stop producers / schedulers / consumers from accepting new work
       |
       v
Executor rejects new submissions
       |
       v
Wait for in-flight tasks within deadline
       |
       +-- Completed: commit/checkpoint/cleanup
       |
       +-- Timed out: interrupt/cancel, record unfinished tasks
       |
       v
Close DataSource, HTTP clients, broker resources
       |
       v
ApplicationContext finishes closing
```

This is a **target sequence**; actual lifecycle callbacks depend on bean types, phases, dependency ordering, and configuration. Spring Boot and Spring Framework provide `SmartLifecycle`/`LifecycleProcessor` to coordinate start/stop. Creating pools outside the container makes participating in this mechanism difficult.

### 13.1. Difference between Spring stop and destroy

- `SmartLifecycle.stop(Runnable callback)` can participate in the **coordinated stop phase**; the callback must run once stopping finishes.
- `@PreDestroy` or `DisposableBean.destroy()` runs in the **bean destruction phase**, not a pause command.
- `ThreadPoolTaskExecutor` inherits lifecycle/destroy support with options for early coordination or waiting during shutdown.
- `setWaitForTasksToCompleteOnShutdown(true)` affects coordinated lifecycle stop behavior; consult the exact Spring 6.1 Javadoc when combining flags.

For an executor with multiple dependent resources, do not pick arbitrary phase numbers: define who **stops submitting** first, who **waits** for tasks, and who **closes underlying resources** last.

### 13.2. Kubernetes deadlines

A container receiving `SIGTERM` usually gets a grace period before the platform forcibly terminates it. If `executor.awaitTermination` is set to 60 seconds while the deployment grants only 30 seconds, you cannot expect every task to finish. Coordinate:

- Load balancer/ingress draining time.
- `server.shutdown=graceful` if running a web server and time for in-flight requests.
- `spring.lifecycle.timeout-per-shutdown-phase` for `SmartLifecycle` phases.
- Executor/scheduler await-termination periods.
- `terminationGracePeriodSeconds` and infrastructure deadlines.
- Time to commit checkpoints/offsets if using durable queues.

Do not naively add timeouts together as a guaranteed total; phases may run concurrently or sequentially per lifecycle, and infrastructure still enforces a hard deadline.

## 14. Bounded queues, rejection, backpressure, and task backlogs

An unclosed pool is one kind of leak; a pool with an **unbounded queue** can also exhaust memory while thread counts appear stable.

With `ThreadPoolExecutor`:

1. Create threads up to `corePoolSize` as needed.
2. Once core threads exist, attempt to enqueue tasks.
3. When the queue is full, spawn threads up to `maximumPoolSize`.
4. When no space remains, invoke `RejectedExecutionHandler`.

That is the standard flow for a bounded blocking queue. With an unbounded queue, scaling up to max may almost never occur; thus `maxPoolSize=100` helps nothing if core size is 8 and the queue accepts infinite work.

### 14.1. JDK rejection policies

| Policy | Behavior | Risks to evaluate |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Caller must handle errors/HTTP statuses/retries explicitly |
| `CallerRunsPolicy` | Under valid conditions, caller executes the task itself | Can block HTTP threads; may drop tasks during shutdown |
| `DiscardPolicy` | Drops the new task | Silent work loss if untracked |
| `DiscardOldestPolicy` | Drops oldest queued task and retries | Can break ordering and lose tasks |

For business work requiring tracking, prefer **explicit visible rejection** and intentional responses over silent discards. When workloads exceed an in-memory pool, a durable message queue and dedicated workers fit better.

### 14.2. TaskRejectedException in Spring

With `ThreadPoolTaskExecutor`, rejections can surface as Spring's `TaskRejectedException` (related to JDK `RejectedExecutionException`). Callers must define handling:

- Return HTTP 429/503 per contract.
- Retry with backoff if safe.
- Persist the task into a durable queue.
- Rate-limit input at the API layer.
- Reject new work when the instance is stopping.

Never catch every exception and return `202 Accepted` if the work **was never accepted**.

## 15. Handling interrupts and cancellation inside tasks

Tasks can actively check interruption:

```java
public void performLoop() {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            doOneUnitOfWork();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            break;
        }
    }
}
```

This is an illustrative snippet inside a business class: `doOneUnitOfWork()` is an application/library-defined method **capable of throwing InterruptedException**. No such method exists in standard Java, so the snippet is not standalone.

Notes:

- If an API **throws `InterruptedException`**, obey the cancellation contract and usually restore the interrupt flag when not propagating further.
- If the task is inside a transaction, ensure proper rollback/cleanup.
- Never swallow interrupts in an infinite loop.
- Some I/O operations do not stop immediately on interrupt, requiring explicit timeouts/cancellation.
- Stop workers only once data/offset/checkpoint invariants are safely handled.

### 15.1. Future.cancel(true) does not replace executor management

`Future.cancel(true)` only requests canceling **one specific task**. The executor can still accept new tasks and retain worker threads. At application end, you must still shut down **the executor itself** under its proper owner.

### 15.2. ThreadLocal and MDC

Thread pools reuse workers. If a task places data into `ThreadLocal`/MDC/security context without clearing it, the next task may see the prior task's context, causing wrong logs or cross-request data leaks.

Use `try/finally` to clear set data; in Spring, use `TaskDecorator` to propagate and clean context properly. Shutting down the pool terminates threads, yet **does not prevent** context leaks between tasks while the pool is running.

## 16. @Async: common misconceptions

### 16.1. @Async must be enabled and invoked via proxy

In default proxy usage, you need `@EnableAsync` and calls to the annotated method going through a Spring proxy. Calling `this.methodAnnotatedAsync()` inside the same bean can bypass the proxy and run synchronously.

Merely annotating a method with `@Async` **does not guarantee** it uses the intended executor. With multiple `Executor` beans, precedence, qualifiers, and bean names affect pool selection.

Use `@Async("businessExecutor")` or `AsyncConfigurer` when explicit targeting is required.

### 16.2. Do not fire-and-forget without error handling

Exceptions in `@Async void` methods may not propagate directly to callers; Spring provides `AsyncUncaughtExceptionHandler` to handle uncaught exceptions from `void` methods.

For work needing outcome confirmation, prefer `Future`/`CompletableFuture` or stateful job systems. Never treat returning HTTP 202 from a controller as proof the task succeeded.

### 16.3. @Async does not come with a durable queue

An in-memory executor loses its queue contents if the process receives `SIGKILL` or a node dies. If tasks must not be lost, persist work into a durable store before returning acknowledgment. An executor is solely responsible for **execution**, not acting as a transaction log.

## 17. Observing executors in production

Monitor both throughput and stopping ability:

| Metric | What it helps diagnose |
| --- | --- |
| Active thread count | How many workers are busy |
| Pool size/current threads | How far the pool has scaled |
| Queue size/capacity | Whether backlog is steadily growing |
| Completed task count | Completion rate |
| Rejected task count | Overload or late submissions during shutdown |
| Task duration p95/p99 | Which tasks are running slow |
| Task errors/timeouts | Whether background failures are being missed |
| Executor shutdown duration | How long pool closing takes |
| Still-running task count | Whether tasks ignore interrupts or block indefinitely on I/O |
| JVM thread count | Whether threads leak across context reloads |

`ThreadPoolTaskExecutor` provides APIs like `getPoolSize()`, `getActiveCount()`, and `getQueueSize()` to inspect the live pool. Specific metrics in Actuator/Micrometer depend on configuration and meter binders; **do not assume** every custom executor automatically exports all metrics without configuring observability.

### 17.1. Finding thread leaks

Common symptoms:

- The JVM does not exit even after `ApplicationContext.close()` was called.
- Thread counts climb after repeated test runs or redeployments.
- Many threads named `pool-123-thread-1` appear with names giving no owner clue.
- Heap dumps retain references to old classloaders via thread/context links.
- Logs report shutdown callbacks finished while the executor still shows `isTerminated() == false`.

How to resolve: capture a thread dump, assign meaningful thread-name prefixes, locate where the pool was created, and establish clear ownership and real shutdown paths. Do not just raise memory limits or mark every thread as daemon.

## 18. Typical design scenarios

### A. A 30-second file-reading job in a web service

Creating an `ExecutorService` per request accumulates pools. Use a managed pool with a bounded queue; on shutdown, stop accepting new jobs and give running jobs a bounded window to complete or checkpoint. If jobs must survive restarts, move to a durable job queue.

### B. Thousands of requests submitting concurrently to a four-thread pool

Without a queue limit, backlogs can exceed memory. Configure a bounded queue + explicit rejection policy; return appropriate load-shedding responses and monitor p99/task wait.

### C. @Scheduled syncing data every minute

During shutdown, the scheduler should not fire new runs while consumers/data sources are closing. Use a managed `TaskScheduler`, decide how to handle in-flight runs, and checkpoint if needed.

### D. A bean manually creating a ScheduledExecutorService

That bean must still actively call `shutdown` and `awaitTermination` on destroy. Do not expect Spring to manage a private executor field automatically. When suitable, switch to a `ThreadPoolTaskScheduler` bean to join the lifecycle.

### E. Backend database disconnects during shutdown

A task trying to query while the DataSource already closed will fail. Stop producers first, await tasks, and only then close the DataSource; use `SmartLifecycle`/bean dependencies appropriately with meaningful await timeouts.

### F. App in Kubernetes killed before jobs finish

If the app awaits 60 seconds while the platform grants only 30 seconds, `SIGKILL` can cut it off and skip cleanup. Align total deadlines, shorten tasks, add checkpoints, and use durable queues for mandatory work.

### G. Java 21 using virtual threads

Virtual threads do not need the same pool sizing as platform threads, yet tasks still need cancellation, timeouts, and ownership. If creating executors manually, verify lifecycle per JDK version; on Java 17 never use virtual-thread APIs only present in newer releases.

## 19. Misconceptions to avoid

| Misconception | Reality |
| --- | --- |
| "ExecutorService is an object, so GC will clean up threads." | Live thread pools retain threads/resources; shutdown needs an owner. |
| "shutdown() waits for all tasks to finish." | It only initiates graceful shutdown; use awaitTermination to wait. |
| "shutdownNow() always stops all tasks immediately." | Best-effort interruption/cancellation only. |
| "Setting daemon=true counts as cleanup." | Daemons can be cut off abruptly; commit/flush is not guaranteed. |
| "If a @Service holds an executor field, Spring closes it automatically." | The container is unaware of private sub-pools; an owner callback or bean is needed. |
| "@Bean(destroyMethod=shutdown) guarantees tasks finish." | shutdown does not block; an owner await/cancel may be required. |
| "Setting a large maxPoolSize prevents overload." | Unbounded queues can prevent maxPoolSize from ever being reached. |
| "One executor per HTTP request gives good isolation." | Risks thread/queue leaks and resource explosion. |
| "@Async always runs on the pool I just declared." | Proxies, qualifiers, and selection rules govern execution. |
| "@Async void exceptions return to HTTP callers." | Errors go to AsyncUncaughtExceptionHandler, not propagated directly. |
| "@Scheduled jobs automatically provide checkpoints." | Schedulers guarantee neither exactly-once nor persistence. |
| "Spring shutdown waits forever for every thread." | Timeouts, lifecycle policies, and container hard deadlines apply. |
| "Raising wait timeouts alone makes data safe." | Idempotency, transactions/checkpoints, and durable queues are needed for critical tasks. |
| "Virtual threads make ownership unnecessary." | Resource bounds, cancellation, and lifecycles still matter. |
| "Executor isShutdown() means isTerminated()." | Tasks may still be running or queued. |
| "CallerRunsPolicy is always safe." | Can block request threads and change behavior during shutdown. |

## 20. Practical checklist

1. Search for calls to `Executors.newFixedThreadPool`, `newCachedThreadPool`, `newSingleThreadExecutor`, `newScheduledThreadPool`, and `new Thread(...)`.
2. For each executor, document its owner and the exact callback that closes it.
3. Prefer Spring-managed `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` for `@Async`/`@Scheduled`.
4. Ensure pools are never created per request or per retry.
5. If using JDK `ExecutorService`, write `try/finally` or an owner bean `@PreDestroy`/destroy method.
6. Remember `shutdown()` stops accepting new tasks **yet does not wait**.
7. After shutdown, use finite `awaitTermination`; define an explicit policy on timeout.
8. With `shutdownNow()`, handle unstarted tasks and running tasks that may ignore interrupts.
9. When using `@Async`, target the right pool and check proxies/self-invocation.
10. Set core/max/queue capacities matching workload; avoid unbounded backlogs.
11. Pick an observable rejection policy with explicit feedback rather than silently dropping tasks.
12. Separate durable jobs from in-memory thread pools if retries across restarts are required.
13. During shutdown, stop producers/consumers from taking new work before closing dependencies.
14. Align await periods with `spring.lifecycle.timeout-per-shutdown-phase` and infrastructure grace periods.
15. Write tasks that honor interrupts, enforce timeouts, and clean up resources.
16. Clear `ThreadLocal`/MDC after each task.
17. Monitor active threads, queues, rejected tasks, task durations, and shutdown latency.
18. Test context close with running tasks, stuck tasks, and rejected tasks.
19. Test deployment restarts/`SIGTERM` in staging; never rely on `SIGKILL` cleanup.
20. On Java 17, never use `ExecutorService` try-with-resources without checking version contracts.
21. Never assume Boot properties automatically configure custom `ExecutorService` instances.
22. Verify correctness/idempotency before declaring a background task "accepted".

## 21. Self-check questions

**1. Why are pools created per request usually dangerous?**

Because each request can spawn its own pool, non-daemon threads, and long-lived queues with no owner closing them when the request ends.

**2. How does shutdown() differ from shutdownNow()?**

`shutdown()` rejects new work while letting old tasks finish; `shutdownNow()` attempts to stop running tasks and skips waiting tasks, without guaranteeing every task stops.

**3. When is awaitTermination() used?**

After requesting shutdown, to wait with a bound until the executor actually terminates.

**4. Does isShutdown() == true mean all tasks finished?**

No. Check `isTerminated()` or the result of `awaitTermination`.

**5. Does Spring automatically close a private ExecutorService field inside a @Service?**

Do not assume so. Add an explicit owner callback or register the executor as a lifecycle-managed Spring bean.

**6. Is @Bean(destroyMethod = "shutdown") sufficient for all business needs?**

No. `shutdown()` does not block; critical work often needs awaiting, cancellation policies, and dedicated checkpoints/transactions.

**7. Why might maxPoolSize=100 only ever use 8 workers?**

An unbounded queue can hold unlimited tasks before scaling toward max triggers. Understand queue capacity.

**8. Does @Async mean tasks survive a pod restart?**

No. `@Async` only changes in-process execution; durable queues/job stores are needed for persistence.

**9. When an @Async method calls another @Async method in the same bean, is it guaranteed asynchronous?**

No. Self-invocation can bypass the Spring proxy.

**10. Can marking threads as daemon replace shutdown()?**

No. Daemon threads can be abruptly terminated by the JVM, losing work and cleanup.

**11. Why must tasks handle InterruptedException?**

Because shutdownNow/cancellation may request interruption; tasks must cooperate to stop, preserve correctness, and release resources.

**12. Does Spring Boot 3.3 provide await-termination properties for task execution/scheduling?**

Yes; `spring.task.execution.shutdown.await-termination` and `spring.task.scheduling.shutdown.await-termination` along with period properties, when using matching auto-configuration.

## 22. Conclusion

```text
Create Executor
     |
Identify single OWNER
     |
Define pool size + bounded queue + rejection
     |
Reuse across tasks
     |
Application begins stopping
     |
Stop accepting new work
     |
shutdown()
     |
awaitTermination(timeout)
     |
   +-- terminated -> cleanup succeeded
   |
   +-- timeout -> shutdownNow() (best effort)
                    |
                    +-- retry/checkpoint/log if needed
     |
ApplicationContext / process stops
```

**Most important rule:** Never create an executor without an **identified owner and cleanup path**. In Spring Boot, use **container-managed pools** and suitable shutdown policies. For manually created Java `ExecutorService` instances, use `shutdown + awaitTermination` inside an owner lifecycle rather than waiting on GC or relying on daemon threads. When background work requires data durability, combine durable queues, checkpoints, idempotency, and infrastructure deadlines.

## Official documentation

- [Java 17 — ExecutorService: shutdown, shutdownNow, awaitTermination](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 — ThreadPoolExecutor and RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.3 — Common Application Properties: spring.task.execution and spring.task.scheduling](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework 6.1 — ExecutorConfigurationSupport shutdown settings](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
