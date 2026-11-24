# Impact of Virtual Threads on Traditional Thread Pool Size Settings in Spring Boot

## 1. The problem to understand

When migrating a Spring Boot application from **platform threads** (OS threads managed by the JVM) to **virtual threads** (Java 21+ virtual threads), many configuration parameters traditionally used to tune thread pools **no longer control the number of concurrent tasks the old way**.

For example, previously a service might use:

```properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=32
spring.task.execution.pool.queue-capacity=100
spring.task.scheduling.pool.size=4
```

If you enable:

```properties
spring.threads.virtual.enabled=true
```

on Java 21+ with **task executor and task scheduler auto-configured by Spring Boot 3.3**, those `pool.*` properties above **are no longer the thread pool tuning knobs for the auto-configured beans**. The reason is that Boot selects different implementations:

- The default task executor switches from `ThreadPoolTaskExecutor` to `SimpleAsyncTaskExecutor` using virtual threads.
- The default task scheduler switches from `ThreadPoolTaskScheduler` to `SimpleAsyncTaskScheduler` using virtual threads.
- Virtual threads are scheduled by the JVM onto a shared set of platform threads, not a dedicated fixed thread pool following the “32 worker threads + 100-task queue” model.
- Limits on concurrent tasks allowed, connection counts, and external system capacity **must still be designed**; only the way they are enforced changes.

**Main warning:** do not infer from `spring.threads.virtual.enabled=true` that **every thread pool in the JVM or every `max-size` setting is disabled**. Only subsystems that **actually switch to the corresponding virtual-thread implementation** lose the meaning of traditional pool parameters. Custom `ThreadPoolExecutor`, JDBC connection pools, Netty event loops, HTTP client pools, and other resource limits still have independent logic.

The scope of this lesson is **Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 21+**, focusing on inspecting and adjusting **thread pool size configurations** when adopting virtual threads.

## 2. Two execution models to distinguish

### 2.1. Traditional platform thread pool

In the thread pool model, the number of active OS-backed threads is managed by an executor:

```text
Submit tasks
     |
     v
ThreadPoolTaskExecutor
     |
     +-- corePoolSize = 8
     +-- maxPoolSize  = 32
     +-- queueCapacity = 100
     |
     +-- Platform worker 1 -> task A
     +-- Platform worker 2 -> task B
     +-- ...
     +-- Platform worker N -> task N
     |
     +-- Waiting queue -> task N+1, ...
```

A blocking I/O task can hold a platform thread for the entire wait duration. Therefore teams commonly configure `core-size`, `max-size`, `queue-capacity`, `keep-alive`, and a rejected-execution policy to manage CPU, resources, and load tolerance.

**Pool tuning knobs here directly apply to that executor.**

### 2.2. Virtual thread-per-task

With the virtual thread-per-task mechanism:

```text
Submit tasks
     |
     v
SimpleAsyncTaskExecutor (virtualThreads=true)
     |
     +-- Virtual thread A -> task A
     +-- Virtual thread B -> task B
     +-- Virtual thread C -> task C
     +-- ...
     |
     v
JVM virtual-thread scheduler
     |
     +-- Shared carrier/platform threads
     +-- Mount/unmount virtual threads when appropriate
```

`SimpleAsyncTaskExecutor` **does not maintain a fixed pool of workers** for reuse like `ThreadPoolTaskExecutor`. Each execution can be given a new thread; when using virtual threads, thread creation cost is far lower than creating platform threads in many situations.

That explains why:

- `pool.core-size` no longer describes how many virtual threads are kept ready.
- `pool.max-size` is no longer the default ceiling on concurrently executing virtual threads.
- `pool.queue-capacity` is no longer a fixed queue in front of `ThreadPoolTaskExecutor`'s worker pool.
- `pool.keep-alive` no longer describes how long idle platform worker threads are kept alive in the default executor.
- Changing the number of virtual threads **is not equivalent** to changing the number of carrier threads or CPU cores.

**Virtual threads do not mean infinite CPU.** CPU-bound work still runs on finite CPUs. The primary benefit is managing many **blocking I/O** tasks without holding a separate platform thread for each waiting task.

## 3. Which configuration enables virtual threads?

With Spring Boot 3.3 and **JDK 21 or newer**:

```properties
spring.threads.virtual.enabled=true
```

Equivalent in YAML:

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

To run an application driven mainly by scheduled background jobs without non-daemon threads keeping the JVM alive, you can add:

```properties
spring.main.keep-alive=true
```

Virtual threads are daemon threads; they **do not keep the JVM alive by themselves** once all other non-daemon threads have exited. `spring.main.keep-alive=true` is the option Boot provides for scenarios where the application must remain running. Do not add it unconditionally to short-lived CLI tools: a batch job intended to finish and exit normally should not wait forever.

### 3.1. Configuration is insufficient if the runtime does not match

- Java 17 **does not have Java 21's virtual threads API**; the application must run on JDK 21+.
- Check both the JDK running Gradle/Maven and **the actual runtime JVM** of the process.
- Do not conclude virtual threads are active just because the property exists; verify **the executor type** and `Thread.currentThread().isVirtual()` inside the code that actually runs.
- A starter/library may register a custom executor or scheduler; in that case the property does not necessarily switch custom beans to virtual.
- A program explicitly calling `Executors.newFixedThreadPool(8)` still creates a pool per its code; Boot does not rewrite that Java method call.
- Pick Java 21+ and a compatible Boot version; do not take a Java 21 example and claim it runs on Java 17.

### 3.2. Application-wide configuration does not change every execution path

`spring.threads.virtual.enabled=true` controls Boot integrations that support virtual threads, not a “JVM switch turning every Thread virtual”.

For example:

- `@Async` uses the executor selected by Spring; if you define your own executor, it can still be a platform-thread pool.
- `@Scheduled` depends on the chosen scheduler; when Boot auto-configures on Java 21 with the flag enabled, that is `SimpleAsyncTaskScheduler`.
- Servlet containers have virtual-thread integration paths depending on server type/version.
- Spring WebFlux with Reactor Netty retains its own event-loop model; it does not turn the entire event loop into virtual threads.
- Database connection pools like HikariCP manage **connections**, not virtual thread counts.
- Remote services still have their own connection/throughput/rate limits.

## 4. Table of changes for Boot 3.3 pool properties

According to Spring Boot 3.3's Common Application Properties list, the following properties **have no effect on the auto-configured task executor when virtual threads are enabled**:

| Property | When using `ThreadPoolTaskExecutor` | When auto executor uses virtual threads |
| --- | --- | --- |
| `spring.task.execution.pool.core-size` | Number of core worker threads | **No longer takes effect** |
| `spring.task.execution.pool.max-size` | Ceiling on worker threads when pool growth conditions are met | **No longer takes effect** |
| `spring.task.execution.pool.queue-capacity` | Task queue capacity | **No longer takes effect** |
| `spring.task.execution.pool.keep-alive` | Duration idle workers are kept alive | **No longer takes effect** |
| `spring.task.execution.pool.allow-core-thread-timeout` | Allows core workers to expire when idle | **No longer takes effect** |

For the **auto-configured scheduler**:

| Property | When using `ThreadPoolTaskScheduler` | When using `SimpleAsyncTaskScheduler` |
| --- | --- | --- |
| `spring.task.scheduling.pool.size` | Number of threads in the scheduler pool | **No longer takes effect** |

**Scope of the “no longer takes effect” statement:** the corresponding auto-configured beans once Boot selects `SimpleAsyncTaskExecutor`/`SimpleAsyncTaskScheduler`. If the application has a manually created executor/scheduler, inspect **that bean's own configuration** and implementation API; do not use this table to claim every pool in the JVM ignores configuration.

### 4.1. Why might max-size already have been ineffective even before virtual threads?

Even in the traditional `ThreadPoolTaskExecutor` model, `max-size` **may not limit as you expect** if the queue is unbounded. When core threads are all busy yet the queue keeps accepting tasks, the pool normally does not grow to maximum. Therefore changing:

```properties
spring.task.execution.pool.max-size=100
```

without checking `queue-capacity` earlier could already have produced unexpected results.

After switching to virtual threads, the situation changes completely: `max-size` no longer controls `SimpleAsyncTaskExecutor` at all. When auditing old configuration, distinguish **properties that used to take effect and are now ignored** from **properties that previously did not control behavior as assumed**.

### 4.2. Does keeping old properties in the file cause startup errors?

Normally, leaving a valid property such as `spring.task.execution.pool.max-size=16` in place does not cause a startup error just because Boot selects a virtual executor. The greater concern is **the operations team thinking the limit of 16 still protects downstream** when it no longer applies to the auto-configured executor.

Therefore, configuration audits must examine **runtime semantics**, not just whether startup has property binding errors.

## 5. What does the auto-configured task executor switch to?

Spring Boot 3.3 describes the task execution mechanism:

- If no matching custom `Executor` causes auto-configuration to back off, Boot auto-configures an `AsyncTaskExecutor`.
- When virtual threads are **off**, the implementation is typically `ThreadPoolTaskExecutor`.
- When virtual threads are **on** on Java 21+, the implementation is `SimpleAsyncTaskExecutor` using virtual threads.

The auto-configured `AsyncTaskExecutor` can be used by integrations such as:

- `@EnableAsync` / `@Async` methods per executor selection rules.
- Spring MVC async processing in matching integration paths.
- Certain async mechanisms in Spring for GraphQL.
- Appropriate blocking execution support in Spring WebFlux.

**Not every async call is guaranteed to go through this bean.** If there is a separate `Executor` bean, `AsyncConfigurer`, an executor specified by qualifier, or another framework subsystem, bean selection rules can differ.

### 5.1. Traditional platform pool configuration

```properties
spring.threads.virtual.enabled=false
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=16
spring.task.execution.pool.keep-alive=30s
```

In an application without a custom executor, these are the properties for the auto-configured `ThreadPoolTaskExecutor`.

From an execution standpoint, you can picture:

```text
Up to 4 core threads (and ability to scale up to 8)
Queue has 16 slots
Additional tasks may be rejected when capacity is exhausted
```

This is a simplified model. Exactly when scaling from core to maximum happens depends on `ThreadPoolExecutor` rules: normally core threads are used first, then the queue, then additional threads once the queue is full, and finally rejection when no capacity remains.

### 5.2. Configuration with virtual threads enabled

```properties
spring.threads.virtual.enabled=true

# The traditional pool properties below do not govern
# the auto-configured SimpleAsyncTaskExecutor:
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=16
spring.task.execution.pool.keep-alive=30s
```

**Do not** leave the four properties above with a comment “limits executor to 8 tasks”. They do not impose an equivalent concurrency limit when virtual threads are enabled.

A clearer configuration:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.simple.concurrency-limit=32
```

`spring.task.execution.simple.concurrency-limit` is a property provided by Spring Boot 3.3 for `SimpleAsyncTaskExecutor`. It **limits the number of concurrent executions** passing through the corresponding executor; it is a **concurrency limiter** concept, not a worker thread pool size. Nor does it mean a limit of 32 requests across the entire application if there are entry points that do not use this executor.

### 5.3. How does the simple executor's concurrency limit work?

With `SimpleAsyncTaskExecutor`:

- The implementation has no worker-reuse pool like `ThreadPoolTaskExecutor`.
- `setConcurrencyLimit(int)` bounds the number of concurrent executions; by default it is normally unbounded if unconfigured.
- When the limit is reached, the limit mechanism's default policy can **make the task submitter wait** rather than spawning another task thread immediately. Do not assume it works like an old bounded queue with a rejection policy.
- Once a task completes, the concurrency slot is released.
- If producers submit tasks faster than completion rate over a sustained period, waiting and backpressure must still be monitored.

**Important:** concurrency limits cannot replace capacity planning for databases, HTTP clients, CPU, or memory. A limit of 32 at the executor applies only to **tasks passing through that exact executor**.

## 6. How does the auto-configured scheduler change?

When using `@EnableScheduling` and Spring Boot needs to auto-configure a scheduler:

- Virtual threads off → `ThreadPoolTaskScheduler` (per pool config).
- Virtual threads on → `SimpleAsyncTaskScheduler` using virtual threads, without a traditional pool of scheduler threads.

Old config example:

```properties
spring.task.scheduling.pool.size=8
```

When `SimpleAsyncTaskScheduler` is selected, the property above **does not create eight scheduler worker threads**. Do not conclude the scheduler is running eight concurrent scheduled tasks solely from this line.

### 6.1. SimpleAsyncTaskScheduler mechanism

Spring Framework 6.1's `SimpleAsyncTaskScheduler` works in a specific way:

```text
A single scheduler thread coordinates triggers
        |
        +-- fixed-rate/cron task #1 -> separate execution thread
        +-- fixed-rate/cron task #2 -> separate execution thread
        +-- fixed-rate/cron task #3 -> separate execution thread
        |
        +-- fixed-delay tasks -> execute on the
                                single scheduler thread
```

For the virtual-thread model, Spring Framework recommends **fixed rate or cron** over **fixed delay** for work needing concurrent execution. `fixedDelay` on `SimpleAsyncTaskScheduler` executes on **the single scheduler thread** to preserve fixed-delay semantics, which can become a bottleneck if a job blocks for a long time.

**Do not claim every `@Scheduled` task automatically runs in parallel.** Trigger type, scheduler bean, and method invocation determine actual concurrency.

### 6.2. Simple scheduler property

Spring Boot 3.3 also provides:

```properties
spring.task.scheduling.simple.concurrency-limit=16
```

This property belongs to the `simple` group, not `pool`. It only takes effect when the corresponding scheduler implementation uses that limit mechanism; it is not a guarantee that every cron job or Quartz job across the application is capped at 16.

At the same time, inspect `@Scheduled(fixedDelay=...)` because it still retains its special dispatch behavior on `SimpleAsyncTaskScheduler`. Declaring a concurrency limit does not turn fixed-delay into fixed-rate.

### 6.3. Example of two configurations

**Platform scheduler:**

```properties
spring.threads.virtual.enabled=false
spring.task.scheduling.pool.size=4
```

**Virtual-thread-aligned scheduler:**

```properties
spring.threads.virtual.enabled=true
spring.task.scheduling.simple.concurrency-limit=16
```

These two snippets are **two configurations for comparison**; do not place both `spring.threads.virtual.enabled` values in the same file expecting clear behavior. When benchmarking, launch two separate processes with each configuration individually.

## 7. Runnable Java 21 / Spring Boot 3.3 example: proving executor type

This section provides a small application **without creating a custom Executor bean**, so Spring Boot chooses the executor automatically. We observe:

1. The class of the `applicationTaskExecutor` bean auto-configured by Boot.
2. `Thread.currentThread().isVirtual()` **right inside the task** executed by the executor.

The output does not depend on multi-task ordering because there is only one future with a timeout.

### 7.1. Project structure

```text
virtual-pool-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          vthreads/
            VirtualPoolApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'virtual-pool-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

The configuration requires a JDK 21+ and a compatible Gradle wrapper. Spring Boot 3.3.13 is used to illustrate APIs from the 3.3 branch; it is not a recommendation to pick an end-of-life version for new projects.

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR

spring.threads.virtual.enabled=false

spring.task.execution.pool.core-size=2
spring.task.execution.pool.max-size=4
spring.task.execution.pool.queue-capacity=8
```

### 7.2. Full source code

`src/main/java/demo/vthreads/VirtualPoolApplication.java`:

```java
package demo.vthreads;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;

@SpringBootApplication
public class VirtualPoolApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(VirtualPoolApplication.class, args)) {
            // Close context after the runner finishes checking.
        }
    }

    @Bean
    ApplicationRunner inspect(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {

        return args -> {
            System.out.println("executor.type="
                    + executor.getClass().getSimpleName());

            CompletableFuture<Boolean> result =
                    new CompletableFuture<>();

            executor.execute(() -> {
                result.complete(Thread.currentThread().isVirtual());
            });

            boolean virtual = result.get(5, TimeUnit.SECONDS);
            System.out.println("task.isVirtual=" + virtual);
        };
    }
}
```

The program defines no custom `Executor` bean, allowing us to observe default auto-configuration. `AsyncTaskExecutor` supports `execute(Runnable)`; `CompletableFuture` transfers the boolean result from worker to runner in a thread-safe manner, and `get(5, TimeUnit.SECONDS)` prevents waiting indefinitely.

Using `try-with-resources` is appropriate here because this is a **short CLI demo**. In a long-lived web service, do not close the context immediately after `run(...)`.

### 7.3. Run with platform threads

With the included Gradle wrapper:

```bash
./gradlew bootRun
```

The lines printed by **application code** when the demo's auto-config is left intact:

```text
executor.type=ThreadPoolTaskExecutor
task.isVirtual=false
```

Additional logs from Gradle/Spring may appear. The class name here is `getSimpleName()` of the Boot-selected implementation. This is the demo's behavior **with no custom Executor bean**; do not apply that output to applications that replaced the executor with their own bean.

### 7.4. Run with virtual threads

Launch a new process:

```bash
./gradlew bootRun --args='--spring.threads.virtual.enabled=true'
```

Then the lines printed by code:

```text
executor.type=SimpleAsyncTaskExecutor
task.isVirtual=true
```

**This is the evidence to verify**: the executor class changes and the thread running the task is virtual. The `spring.task.execution.pool.*` properties are still in the config file, yet **are not used to create a pool with core=2, max=4, queue=8 for the new executor**.

Note that Gradle, CMD, and PowerShell have different quoting rules; adjust quotes when running in your shell. You can also change the property directly in the file and re-run if passing via `--args` is inconvenient.

### 7.5. Why not print platform worker counts from a thread dump and draw conclusions?

Virtual threads are **mounted/unmounted** onto platform carrier threads on demand. The number of carrier threads when a snapshot is taken:

- Does not equal the number of live virtual threads.
- Is not a cap on requests, tasks, or database connections.
- Can vary with CPU, load, and runtime behavior.
- Can be affected by blocking/pinning and other JVM activity.

`Thread.currentThread().isVirtual()` measures **the thread type executing the current task**, while `executor.getClass()` tells you **the bean implementation**. Combining both measurements is better than just counting thread lines in logs.

## 8. Example verifying scheduler pool.size property no longer has meaning

If you want to study the scheduler, create a standalone demo application with `@EnableScheduling`, a `@Scheduled` bean, and let Boot auto-configure the scheduler.

Configuration snippet:

```java
@Configuration
@EnableScheduling
class SchedulingConfig {

    @Scheduled(fixedRate = 5000)
    void heartbeat() {
        System.out.println("scheduled.isVirtual="
                + Thread.currentThread().isVirtual());
    }
}
```

This is a snippet placed in an appropriate package class, requiring imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
```

Add once to a Spring Boot project where the bean is not excluded by scanning/conditional configuration. With `SimpleAsyncTaskScheduler` and virtual threads, **fixed-rate execution** aligns with the thread-per-task mechanism. The `scheduled.isVirtual=...` lines depend on timing and the actual scheduler, so **no fixed stdout is asserted** like the `ApplicationRunner` demo in section 7.

Try two configurations:

```properties
# Run A: platform scheduler
spring.threads.virtual.enabled=false
spring.task.scheduling.pool.size=2
```

```properties
# Run B: virtual-thread scheduler
spring.threads.virtual.enabled=true
spring.task.scheduling.pool.size=2
```

In run B, `pool.size=2` does not turn the auto scheduler into two platform worker threads. That is a change in the underlying scheduler backend rather than a parsing bug.

**Do not use a single task to infer maximum parallelism.** To verify concurrency, you need multiple triggers/tasks or controlled load along with a recorder measuring active tasks at each point in time.

## 9. Limiting concurrency without a fixed thread pool

A common mistake when enabling virtual threads is removing all limits because “threads are cheap”. Virtual threads make **waiting on I/O** cheaper, yet downstream resources remain finite:

```text
10,000 virtual threads
         |
         +-- Database connections: 20
         +-- HTTP client max connections: 100
         +-- Remote service rate limit: 500 requests/minute
         +-- CPU cores: finite
         +-- Heap / native memory: finite
         +-- File descriptors: finite
```

If all 10,000 tasks simultaneously need a database connection, **the database does not automatically gain 10,000 connections**. Many tasks will wait or time out, and the system may experience higher memory/latency.

### 9.1. Spring Boot's concurrency limit

On the auto-config SimpleAsyncTaskExecutor path:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.simple.concurrency-limit=32
```

This limit helps control the number of concurrent task executions **through the corresponding task executor bean**. It does not automatically throttle:

- A servlet controller using a different dispatch path.
- A scheduled task not using this executor.
- Code calling `Thread.startVirtualThread(...)` directly.
- Custom `ExecutorService` beans not going through the auto-config bean.
- JDBC connection pools and network clients.

Therefore limits must be placed right **where tasks are submitted or at the resource that needs protection**.

### 9.2. Semaphore to limit a resource

One way to limit **concurrent operations** independently of the executor is using a `Semaphore`.

Standalone Java 21 example, file `PermitDemo.java`:

```java
import java.util.concurrent.Semaphore;

public class PermitDemo {

    private static final Semaphore PERMITS = new Semaphore(2);

    public static void main(String[] args) throws InterruptedException {
        Thread t1 = Thread.ofVirtual().start(() -> guarded("A"));
        Thread t2 = Thread.ofVirtual().start(() -> guarded("B"));
        Thread t3 = Thread.ofVirtual().start(() -> guarded("C"));

        t1.join();
        t2.join();
        t3.join();

        System.out.println("all.done");
    }

    private static void guarded(String name) {
        boolean acquired = false;

        try {
            PERMITS.acquire();
            acquired = true;

            System.out.println("entered=" + name
                    + ", virtual=" + Thread.currentThread().isVirtual());
            Thread.sleep(100);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            if (acquired) {
                PERMITS.release();
            }
        }
    }
}
```

Run:

```bash
javac PermitDemo.java
java PermitDemo
```

**Output has no fixed order** among the `entered=A`, `entered=B`, `entered=C` lines because thread scheduling is concurrent. All three `entered=...` lines yield `virtual=true`, and the final line is:

```text
all.done
```

Semaphore allows at most **two tasks past `acquire()` concurrently** at a time. It does not limit how many virtual threads are created; the third task may be waiting for a permit. So if upstream continuously spawns more virtual threads faster than downstream drains, you still need **backpressure and input admission limits**.

In production, add deadlines, cancellation, metrics, a fairness policy if needed, and proper handling of operation exceptions. `Thread.sleep(100)` only simulates a wait in the demo, not a production I/O pattern.

### 9.3. Do not unconsciously rely on a platform thread pool as a substitute semaphore

Previously, an application might **rely on maxPoolSize=16** to “implicitly” cap requests sent to an API. When switching to virtual-thread-per-task, that barrier vanishes if it only lived in `spring.task.execution.pool.max-size`.

The solution must be redesigned:

- Use a concurrency limiter/`Semaphore` tied to that API.
- Use a rate limiter when the external system enforces **requests/second** rather than concurrency.
- Use bounded queues and rejection/backpressure if ingress exceeds service throughput.
- Set connection pool sizes, timeouts, and retry policies aligned with the dependent service.
- Monitor active tasks and tasks waiting for permits, not just JVM thread counts.

## 10. Which traditional thread pools remain in effect?

**Not every thread group disappears.** The table below is key when auditing an application:

| Component | When virtual threads are enabled in Boot | Tuning conclusion |
| --- | --- | --- |
| Auto `applicationTaskExecutor` | Usually uses virtual `SimpleAsyncTaskExecutor` | `spring.task.execution.pool.*` no longer applies |
| Auto scheduler when needed | Usually uses virtual `SimpleAsyncTaskScheduler` | `spring.task.scheduling.pool.size` no longer applies |
| Custom `ThreadPoolTaskExecutor` | Remains the app-created bean unless you replace it | The **custom bean's** `corePoolSize`/`maxPoolSize` can still take effect |
| Custom `ThreadPoolTaskScheduler` | Not auto-replaced by Boot just from the global virtual flag | The **custom scheduler's** pool config can still take effect |
| `Executors.newFixedThreadPool(n)` | Creates a platform thread pool per code | `n` remains meaningful |
| `Executors.newVirtualThreadPerTaskExecutor()` | Each task gets a virtual thread | No traditional pool size n |
| HikariCP | Manages database connections | `maximumPoolSize` is connection count; still needs tuning |
| HTTP client connection pool | Manages connections/rates to other servers | Connection limits still apply |
| Reactor Netty event loops | Independent event-loop model | Does not auto-convert to virtual-thread-per-task from the flag |
| Rate limiter / semaphore | Controls work entering a resource | Still needed to protect downstream |
| CPU-bound worker pool | Depends on specific executor | Many virtual threads do not create extra CPU cores |

The table reflects **configuration models**, without intending to generalize identically to every server/client library. For each component, inspect the runtime executor class and version-accurate documentation.

### 10.1. Custom ThreadPoolTaskExecutor example

```java
@Configuration
class CustomExecutorConfig {

    @Bean("legacyExecutor")
    ThreadPoolTaskExecutor legacyExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("legacy-");

        return executor;
    }
}
```

This snippet requires importing `Configuration`, `Bean`, and `ThreadPoolTaskExecutor`. When Spring manages the bean lifecycle, the implementation can initialize through the corresponding bean factory mechanism.

**Note:** simply setting `spring.threads.virtual.enabled=true` **does not turn this bean into SimpleAsyncTaskExecutor**. It remains a custom `ThreadPoolTaskExecutor` with a configurable pool.

Some Spring Boot auto-configs have back-off rules when a custom `Executor` bean exists. Thus adding this configuration snippet alone can **change the auto task executor bean** and how `@Async` selects its executor. Do not inject it into section 7's demo when the goal is observing default auto-config.

### 10.2. JDBC connection pool is not a thread pool

Example:

```properties
spring.datasource.hikari.maximum-pool-size=20
```

This property limits **database connections in HikariCP** when Hikari is configured, not virtual thread count. A connection held for a long time still blocks other tasks. If the application creates 5,000 virtual threads querying the database concurrently, throughput can bottleneck at 20 connections (plus database limits), rather than connection pools scaling infinitely because of virtual threads.

Monitor:

- Active/idle/pending connections.
- Connection acquisition wait time.
- SQL query latency and transaction duration.
- Timeouts, retries, and pile-ups of tasks waiting on the database.
- Actual concurrent requests flowing through the service.

**Do not confuse** `spring.datasource.hikari.maximum-pool-size` with `spring.task.execution.pool.max-size`. One limits connections; the other previously bounded a thread executor implementation.

## 11. Servlet servers: do not apply one formula across Tomcat/Jetty/Undertow

Some server settings use the name “threads”:

```properties
server.tomcat.threads.max=200
server.tomcat.threads.min-spare=10
```

In the traditional Tomcat platform executor model, these values tune the request-handling pool. When using a compatible Spring Boot/Tomcat virtual-thread integration, request execution can go through a virtual-thread executor, so **traditional platform-thread worker limits no longer describe the allowed virtual requests** in the old way.

However, avoid blanket one-sided claims that **all `server.*.threads.*` are always ignored**:

- It still depends on the actual server running (Tomcat/Jetty/Undertow/others).
- It depends on the Boot and embedded-server versions.
- It depends on whether the application has custom connectors or executors.
- Acceptors, pollers, selectors, event loops, or I/O workers may still be platform threads.
- `max-connections`, request queues, timeouts, or connector-specific limits may still be active.

**Right approach:** identify the server, connector executor, runtime version, and measure in practice. Do not issue a blanket recommendation to “delete all server thread configs” based solely on the global flag.

### 11.1. WebFlux and event loops

Reactor Netty uses event loops. When enabling `spring.threads.virtual.enabled`, do not treat the entire reactive pipeline as having switched to one virtual thread per request. Blocking execution integration can use Boot's task executor at supported points, yet event-loop architecture is a different matter.

If you are already using reactive non-blocking properly, optimizing thread-per-request is not a reason to replace the entire model. Conversely, if you put blocking JDBC or REST calls onto an event-loop thread without proper offloading, enabling virtual threads **does not fix blocking-the-event-loop bugs**.

### 11.2. Request concurrency still needs guardrails

Even when requests are handled by virtual threads, a service may still need:

- Per-endpoint in-flight request limits.
- TCP and HTTP connection limits.
- Client and downstream rate limits.
- Circuit breakers/bulkheads.
- Overall timeouts and per-I/O-operation timeouts.
- Quotas for CPU/heap workloads.
- Mechanisms to reject or slow request intake when the system is saturated.

Cheap threads do not make database queries or remote API calls free.

## 12. Why can keeping the old max-size overload the system?

Suppose previously the system had:

```properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
```

The team thought this was a “bulkhead” capping concurrent downstream tasks at 16. After enabling:

```properties
spring.threads.virtual.enabled=true
```

if `@Async` actually uses the auto-configured `SimpleAsyncTaskExecutor`, the pool settings above no longer protect downstream.

Suppose a traffic spike submits 2,000 tasks, each calling an HTTP service:

```text
BEFORE:
  Platform-thread pool executor
  -> can use at most a finite number of workers
  -> queue/rejection per configuration

AFTER:
  Virtual thread-per-task executor
  -> can spawn many more virtual tasks
  -> more concurrent calls if no new limit exists
  -> downstream stalls or returns 429/503/timeout
```

This is an **illustrative scenario**, not a guarantee every app will hit 2,000 concurrent calls: client connection pools and other limits may still intervene.

**Lesson:** when removing the physical cap of a thread pool, you must decide where **business/infrastructure limits** should reside. You can use `spring.task.execution.simple.concurrency-limit` or dedicated per-downstream limits.

## 13. CPU-bound and I/O-bound: tune according to the bottleneck

### I/O-bound work

Examples:

- Calling a database and waiting for query results.
- Calling an external API and waiting for a network response.
- Reading files via appropriate blocking APIs.
- Waiting for messages or results from external systems.

Virtual threads generally suit sequential blocking coding styles for such tasks. However, **throughput remains bounded** by the DB, HTTP client, network, rate limits, timeouts, and the serving party.

### CPU-bound work

Examples:

- Heavy encryption/decryption.
- Image resizing, large numerical processing.
- Algorithmic computation.
- Pure-CPU data transformation.

If the CPU has 8 cores and 5,000 tasks execute computation concurrently, virtual threads do not create extra CPUs. A **bounded CPU executor** or CPU-based concurrency cap may still be appropriate.

There is no universal rule like “with virtual threads, set max-size=1,000,000” for all workloads. Measure and classify workloads first.

### Pinning in Java 21

A virtual thread can become **pinned** to its carrier thread in certain execution sections, such as `synchronized` blocks under specific conditions or native/foreign code. When pinned and encountering blocking, the carrier is not released as expected, reducing concurrency efficiency.

On Java 21, use JFR events related to virtual-thread pinning and appropriate JVM diagnostics to identify bottlenecks. Do not assume simply adding virtual threads will raise throughput. Newer Java versions may alter pinning behavior, so read the corresponding JVM documentation when upgrading.

## 14. Configuration table: what to keep, remove, or change?

| Configuration | Action when migrating auto tasks to virtual |
| --- | --- |
| `spring.task.execution.pool.core-size` | Remove from descriptions of virtual executor limits; keep only if another pool still truly needs it |
| `spring.task.execution.pool.max-size` | Stop treating it as a bulkhead; replace with an appropriate concurrency limit |
| `spring.task.execution.pool.queue-capacity` | Stop treating it as SimpleAsyncTaskExecutor's bounded queue |
| `spring.task.execution.pool.keep-alive` | Do not tune virtual thread lifecycle with this property |
| `spring.task.execution.pool.allow-core-thread-timeout` | Does not apply to virtual simple executor |
| `spring.task.scheduling.pool.size` | Do not tune SimpleAsyncTaskScheduler with this property |
| `spring.task.execution.simple.concurrency-limit` | Consider if you want to bound tasks through the auto simple executor |
| `spring.task.scheduling.simple.concurrency-limit` | Consider if you need to bound execution of the simple scheduler |
| `spring.task.execution.thread-name-prefix` | Can still be useful for identifying tasks, not pool size |
| `spring.main.keep-alive` | Consider for apps with only daemon virtual threads that must stay alive |
| `spring.datasource.hikari.maximum-pool-size` | **Still needs** tuning to match database capacity |
| HTTP client pool size | **Still needs** tuning to match downstream capacity |
| Custom `ThreadPoolTaskExecutor` props | **Still meaningful** for that custom executor, if used |

Do not simply “delete all `pool.*` lines to tidy the file” without mapping actual executors/schedulers first. In a large application, there may be multiple thread pools from libraries, each with its own policy.

## 15. How to verify configuration actually took effect

Do not just read the properties file. Observe **implementation** and **behavior**.

### 15.1. Check the actual executor bean

In the appropriate context:

```java
AsyncTaskExecutor executor = context.getBean(
        "applicationTaskExecutor", AsyncTaskExecutor.class);

System.out.println(executor.getClass().getName());
```

This is a **snippet inside a method** with an existing `context` variable and `AsyncTaskExecutor` import. If an app has no `applicationTaskExecutor` bean due to custom config, the call will fail; that is a signal to inspect bean selection, not a bug in Java virtual threads.

### 15.2. Check thread type in real work

```java
executor.execute(() -> {
    boolean virtual = Thread.currentThread().isVirtual();
    System.out.println("isVirtual=" + virtual);
});
```

This is a Java 21+ snippet with `executor` of type `AsyncTaskExecutor` or `Executor` passed in. Do not run this on Java 17 where `Thread.isVirtual()` does not exist.

### 15.3. Observe the actual limit

Measure:

- Currently executing tasks and tasks waiting for submission/permits.
- Wait time before a task starts.
- Rejections, timeouts, and cancellations.
- Hikari active/pending connections.
- HTTP client leased/idle connections.
- Request latency P95/P99 and error rate.
- CPU utilization, memory footprint, GC, and pinning status.
- Startup/shutdown of schedulers and executors.

If `max-size=16` remains configured yet active tasks through the auto virtual executor exceed 16 in a proper test, that is **expected behavior** of the switched backend, not a binding bug.

### 15.4. Two configurations, two separate processes

When benchmarking:

1. Run baseline with `spring.threads.virtual.enabled=false`.
2. Record executor/scheduler class, active task count, throughput, and latency.
3. Shut down the application completely.
4. Run again with `true` on Java 21+.
5. Verify executor/scheduler classes and `Thread.isVirtual()` before comparing results.
6. Hold workload, JVM flags, DB connections, CPU, heap, and traffic steady.
7. Do not compare startup logs from run A against a completely different load test in run B.

When a benchmark adds a custom Executor in run B, you are no longer comparing **the same configuration** differing only by the virtual flag.

## 16. Pitfalls with @Async

A class with a method:

```java
@Service
public class ImportService {

    @Async
    public void importFile() {
        System.out.println("async.isVirtual="
                + Thread.currentThread().isVirtual());
    }
}
```

This snippet requires imports for `Service`, `Async`, and appropriate `@EnableAsync` config; separate `ImportService.java` file, compiled with Java 21+.

When there is no custom executor, `@Async` can use the Boot auto-configured executor. Yet there are cases that differ from the demo:

- `@Async("specialExecutor")` selects a different executor if that bean exists.
- `AsyncConfigurer#getAsyncExecutor()` can specify a custom executor.
- Multiple `Executor` beans alter bean selection logic.
- **Self-invocation**: calling an `@Async` method from another method on the **same instance** can bypass the Spring AOP proxy, running the method synchronously on the caller's thread.
- A bean not managed by Spring does not receive the `@Async` proxy.
- Not every async integration in an application runs through `applicationTaskExecutor` under the same rules.

**Mistake to avoid:** “With `spring.threads.virtual.enabled=true`, every `@Async` method definitely runs virtually.” Inspect the actual executor and whether calls traverse the proxy.

## 17. Pitfalls with @Scheduled and fixedDelay

Using Spring Boot's virtual scheduler does not just rename threads. `SimpleAsyncTaskScheduler` behaves differently from `ThreadPoolTaskScheduler`, especially:

```java
@Scheduled(fixedDelay = 1000)
public void pollQueue() {
    // May block while running on the scheduler thread
    // when using SimpleAsyncTaskScheduler.
}
```

This is a method snippet requiring `@EnableScheduling` in config, an appropriate Spring bean, and the `Scheduled` import.

In this model, fixed-delay tasks execute on a single scheduler thread, so a slow task can impact scheduling. If a task needs thread-per-task concurrency, Spring Framework recommends fixed-rate or cron when using virtual SimpleAsyncTaskScheduler.

However, **switching fixedDelay to fixedRate is not a harmless change**. Semantics change:

- `fixedDelay`: waits an interval after the previous run completes.
- `fixedRate`: triggers at intervals measured from start/schedule.
- If each run exceeds the period, overlapping tasks can pile up (depending on scheduler/trigger semantics), overloading downstream or duplicating data processing.
- Cron also has its own scheduling semantics and does not solve idempotency or execution count by default.

When refactoring, determine whether overlapping execution is safe, and add single-flight locks, distributed locks, or concurrency limits if business logic requires them.

## 18. Design limits around resources rather than thread counts

A service may need several distinct limits:

```text
Incoming HTTP requests
       |
       +-- Admission control / rate limiter
       |
       v
Virtual-thread execution
       |
       +-- CPU-intensive work? -> bounded CPU capacity
       |
       +-- DB call? -> Hikari pool + timeout
       |
       +-- External API? -> HTTP client pool + bulkhead/rate limit
       |
       +-- File I/O? -> file descriptors + disk throughput
       |
       v
Response
```

**Principle:** the system must enforce limits at **bottlenecks and resource ownership boundaries**. Traditional thread pools may have accidentally acted as admission control, whereas virtual threads decouple those two functions.

For each downstream dependency, answer:

1. How many concurrent operations maximum are safe?
2. Is there a per-second/per-minute rate limit?
3. When capacity runs out, do we wait, reject, or shed load?
4. Are timeouts and cancellation in place?
5. Are there retries and backoff? Can retries cause traffic storms?
6. When the client disconnects, should the task keep running?
7. During shutdown, how many tasks remain unfinished and do they need draining?
8. Which metrics confirm the limit is actually enforced?

Only after answering these should you choose the limiter and concrete values. There is no universal configuration valid for every workload.

## 19. What if a fixed number of workers is still needed?

There is no rule forcing **every task** onto virtual threads. For CPU-bound work or resources needing dedicated platform threads, a custom bounded executor remains reasonable.

Example:

```java
@Bean("cpuExecutor")
ExecutorService cpuExecutor() {
    return Executors.newFixedThreadPool(
            Runtime.getRuntime().availableProcessors());
}
```

This is a snippet in a `@Configuration` class requiring imports for `Bean`, `Executors`, `ExecutorService`, and proper lifecycle/close config. In Java 21, `ExecutorService` supports `close()` under `AutoCloseable`; when registering a bean via `@Bean`, ensure the container closes the resource or declare `destroyMethod = "close"` if explicitness is desired.

The intent is to create a **bounded platform thread pool** for dedicated CPU-bound work. Introducing this custom `ExecutorService` into the context can affect auto-configured executors per Boot's conditions; choose bean names, `@Qualifier`, and `@Async` semantics carefully.

It is wrong to view this custom pool as “contradicting” virtual threads. Within the same JVM, **different executors can use different concurrency models**.

## 20. Is carrier-thread pool size tuned like pool-size?

No. Virtual threads are scheduled by the JVM onto shared platform carrier threads. Java supporting JVM parameters for the virtual-thread scheduler **does not mean** you use `spring.task.execution.pool.max-size` to tune the carrier scheduler.

If a clear bottleneck is measured at the scheduler, you can study JVM system properties such as `jdk.virtualThreadScheduler.parallelism` on supported JDK versions. However, that is **advanced JVM-level tuning** with different consequences and should not be treated as a one-to-one replacement for per-Spring-executor `core-size`/`max-size`.

Specifically:

- Do not raise carrier parallelism just to “allow more requests” when the real bottleneck is the database.
- Do not lower parallelism to protect a remote API; use a rate/concurrency limiter in the right place.
- Do not change the JVM scheduler in production without benchmarking and measuring pinning/blocking.
- JDK 21 and later versions can differ in virtual-thread pinning behavior and scheduler internals; consult version-accurate documentation.

## 21. When does an old property actually remain effective?

For example, with two executors:

```text
applicationTaskExecutor  -> SimpleAsyncTaskExecutor (virtual)
legacyExecutor           -> ThreadPoolTaskExecutor (platform)
```

If you adjust `legacyExecutor.setMaxPoolSize(8)` in code or bind its own properties, **the custom pool still caps workers** as designed. Yet `spring.task.execution.pool.max-size=8` does not automatically tune all custom executors, nor does it cap the virtual `applicationTaskExecutor`.

A misleading situation:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.pool.max-size=8
```

The team observes CPU-bound tasks still running only 8 platform threads, and concludes `pool.max-size` still works with virtual threads. In reality, those tasks may be running through a 8-thread custom pool unrelated to that property.

Proper verification steps:

1. List all `Executor` / `AsyncTaskExecutor` beans actually present.
2. Check each bean's name and class.
3. Inspect which bean `@Async`/controllers/schedulers/SDKs select.
4. Check the executing thread with `Thread.isVirtual()` at the exact execution site.
5. Only conclude a property takes effect after before/after measurements **on that exact bean and task path**.

## 22. Other parameters that remain useful in task execution

Not the entire `spring.task.execution.*` namespace is meaningless. For example:

```properties
spring.task.execution.thread-name-prefix=task-
spring.task.execution.simple.concurrency-limit=32
```

When supported by the implementation, thread name prefix can aid observability in logs/traces, and concurrency limit can be used to cap parallelism.

Still:

- **Thread name prefix** is not a concurrency limit.
- **Concurrency limit** is not equivalent to queue-capacity or max-size.
- **Shutdown properties** must be reviewed by implementation, version, and task lifecycle; do not extrapolate `ThreadPoolTaskExecutor` behavior to `SimpleAsyncTaskExecutor`.
- Submitted tasks may be waiting on the limiter or I/O; when the context closes, clear cancellation/drain policies are required.
- A blocked virtual thread has not finished; lifecycle and timeouts still apply.

Cross-check **Spring Boot 3.3** property lists rather than mixing properties introduced in later Boot releases into older documentation.

## 23. How to build a meaningful benchmark

Assume an endpoint calls a downstream API taking 200 ms I/O and 2 ms CPU. With a 16-thread platform pool, throughput can be capped by threads held waiting; with virtual threads, waiting does not necessarily occupy carrier threads.

However, results depend on:

- HTTP client connection pool.
- Downstream rate limits.
- Network stack.
- Other database transactions in the request.
- JVM GC and memory.
- Task creation/processing rate.
- Unmountable pinning/blocking.
- Actual CPU count.
- Backpressure and retries.

**Never promise performance gains by a fixed multiplier.** Numbers like 16 threads or 200 ms here are only synthetic figures to guide testing.

### Benchmark procedure

1. Run the same binary on a supported JDK.
2. Test baseline (virtual=false) and virtual=true in **two separate fresh processes**.
3. Record exact executor classes/task virtual states.
4. Keep DB/HTTP pools and request concurrency fixed in the initial comparison.
5. Only afterward vary admission limits and connection pools one variable at a time.
6. Measure throughput, P50/P95/P99 latency, error rate, timeouts, memory, CPU, and GC.
7. Check pinning and task queueing/wait times.
8. Ramp load up to the failure threshold to observe how the system **sheds load**, not only the sweet spot.
9. Reproduce shutdown with in-flight tasks.
10. Document legacy properties that remain present yet have lost effect on auto beans.

Without measuring **error rate** and **downstream saturation**, high request counts in a short benchmark can mask the risk of overloading dependent services.

## 24. Daemon threads and keep-alive issues

Virtual threads are daemon threads. A non-web application with `@Scheduled` and no other non-daemon threads can exit the JVM unexpectedly once the main thread finishes, even when you expect scheduled tasks to keep the process alive.

Spring Boot has:

```properties
spring.main.keep-alive=true
```

to keep the JVM running when only virtual threads remain. This **differs from thread pool sizing**, yet is an operational consequence of switching the scheduler from platform to virtual threads.

In section 7's CLI demo, `main` uses `try-with-resources` to close the context after the runner; keep-alive is omitted because the program is meant to exit on its own. In a long-running scheduled service, clearly establish responsibility for keeping the process alive.

Do not treat keep-alive as a tool guaranteeing tasks finish during shutdown; graceful shutdown requires configuring and implementing proper lifecycle handling.

## 25. Common issues and fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `max-size=16` yet more than 16 virtual tasks observed | SimpleAsyncTaskExecutor does not use pool max-size | Use `spring.task.execution.simple.concurrency-limit` or resource limiters |
| `queue-capacity=100` yet no expected queue | Auto executor switched to simple | Design new bounded admission/backpressure |
| Changing `core-size` does not change startup/throughput | Virtual executor has no core worker pool | Verify implementation, then remove inapplicable properties |
| `keep-alive` does not affect executor | No longer auto ThreadPoolTaskExecutor | Distinguish pool keep-alive from JVM `spring.main.keep-alive` |
| `spring.task.scheduling.pool.size=8` yet scheduled concurrency differs | Auto scheduler is SimpleAsyncTaskScheduler | Use simple concurrency policy, review triggers |
| Slow `fixedDelay` delays other jobs | Fixed-delay runs on a single scheduler thread | Consider controlled fixed-rate/cron |
| Flag enabled yet task is not virtual | Custom Executor, AsyncConfigurer, wrong JVM/config, or self-invocation | Check bean selection and `Thread.isVirtual()` |
| All tasks virtual yet DB still bottlenecks | JDBC connections remain finite | Monitor Hikari metrics, timeouts, and query cost |
| CPU stays 100%, adding tasks does not help | CPU-bound workload | Use bounded CPU executor, optimize algorithm |
| HTTP client returns more 429s | Lost traditional pool bulkhead | Add per-downstream rate/concurrency limits |
| App exits on its own when only scheduler exists | Virtual daemon threads do not hold JVM | Check `spring.main.keep-alive` and lifecycle path |
| App shuts down slowly | Tasks not drained/cancelled properly | Design shutdown and verify timeouts |
| Thread dump shows few carriers yet many tasks | Virtual thread mount/unmount model | Do not equate carrier count with task count |
| `@Async` runs synchronously on caller | Self-invocation or ineffective proxy | Call via Spring proxy or refactor beans |
| Servlets still show platform threads | Server internals/custom connector still platform | Inspect exact executor and server version |
| Reactor Netty still uses event-loop threads | Separate WebFlux reactive stack | Do not infer global flag converts all event loops |
| Heap grows despite few platform threads | Too many virtual tasks waiting/holding state | Bound admissions, reduce retained data and timeouts |
| Boot property and custom executor share context | Auto-config property does not apply to custom bean | Check bean implementation & binding |

A helpful debugging workflow:

1. Check the process's `java -version`.
2. Confirm `spring.threads.virtual.enabled` **at actual runtime**, not just in source files.
3. List `Executor` and `TaskScheduler` beans, looking for custom beans.
4. Inspect executor/scheduler classes and executing thread types.
5. Identify which `pool.*` settings belonged to auto-configured beans that were replaced.
6. Identify limits that previously lived in the old thread pool to redesign admission control.
7. Check downstream pools, timeouts, rate limits, and CPU/memory.
8. Check `@Scheduled` fixed-delay behavior if jobs are slow.
9. Check lifecycle when only daemon virtual threads remain.
10. Re-measure performance before deciding on production configuration changes.

## 26. Practice exercises

### Exercise 1: predict executor class

With configuration:

```properties
spring.threads.virtual.enabled=false
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
```

In an app with no custom Executor bean, what type is `applicationTaskExecutor` by default?

**Answer:** `ThreadPoolTaskExecutor` per Boot 3.3 auto-config.

### Exercise 2: enable virtual while keeping pool properties

Change only `spring.threads.virtual.enabled=true`. Do `pool.core-size` and `pool.max-size` cap virtual tasks at 8?

**Answer:** no. Boot switches the auto executor to virtual `SimpleAsyncTaskExecutor`; those pool properties no longer take effect on that bean.

### Exercise 3: distinguish concurrency limit from pool size

Set:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.simple.concurrency-limit=12
```

Questions:

1. What is being limited?
2. Does the JVM create at most 12 virtual threads?
3. Does a manual `Thread.startVirtualThread(...)` call count toward the same limit?

**Answer:** the limit applies to tasks routed through the corresponding simple executor; it is not a JVM-wide virtual thread cap. Manually spawned threads are not automatically subject to the same limiter.

### Exercise 4: fixed-delay scheduler

Enable `SimpleAsyncTaskScheduler`, set `spring.task.scheduling.pool.size=8`, and write a long-blocking `@Scheduled(fixedDelay=...)`. Why can the task still stall the scheduler despite “pool.size=8”?

**Answer:** pool.size does not apply to the simple scheduler; moreover, fixed-delay tasks can execute on the single scheduler thread. Review scheduling semantics and concurrency design.

### Exercise 5: connection pool

An app has 2,000 virtual tasks calling the database, yet Hikari has at most 20 connections. What happens if all tasks want a connection simultaneously?

**Answer:** they do not automatically become 2,000 DB connections. Tasks that cannot acquire a connection wait/time out per pool policy, potentially raising latency, memory, and errors. Bound in-flight database operations and optimize queries/transactions.

### Exercise 6: custom executor

The application declares a `ThreadPoolTaskExecutor` max 8 and then enables the global virtual flag. Does the custom executor automatically switch to virtual? **No**. Replace the implementation or configure it separately if virtual threads are desired.

### Exercise 7: compare two runs

Run section 7's `VirtualPoolApplication` demo with virtual false and true. Confirm:

```text
false: executor.type=ThreadPoolTaskExecutor
       task.isVirtual=false

true:  executor.type=SimpleAsyncTaskExecutor
       task.isVirtual=true
```

The `false:` / `true:` labels here only **mark the two runs**, not literal text printed by the code. Each run only prints the two lines `executor.type=...` and `task.isVirtual=...`.

### Exercise 8: write a tuning decision

Given a service with 8 CPU cores, Hikari 20, HTTP client max 100 connections, and many `@Async` tasks. Choose:

- Which computational tasks need a bounded CPU pool?
- Is `spring.task.execution.simple.concurrency-limit` needed?
- Are separate database/API limits needed?
- How should timeouts and retries be configured?
- Which metrics should be measured before/after?

The goal is **producing a resource-based limiting plan**, not searching for a new `pool.max-size` number to apply across every subsystem.

## 27. Checklist for migrating from platform pools to virtual threads

- [ ] Actual runtime is Java 21+.
- [ ] Spring Boot version supports it and `spring.threads.virtual.enabled` is verified at runtime.
- [ ] Auto-configured and custom executor/scheduler beans have been inventoried.
- [ ] Do not confuse `spring.task.execution.pool.*` with `spring.task.execution.simple.*` namespaces.
- [ ] Traditional pool properties are no longer documented as limits once auto-config switches to simple executor.
- [ ] `spring.task.scheduling.pool.size` has been evaluated when SimpleAsyncTaskScheduler is selected.
- [ ] `fixedDelay` jobs needing parallel runs or risking scheduler blocking have been audited.
- [ ] `@Async` has been verified to run through Spring proxy and the intended executor.
- [ ] New admission/concurrency limits exist if the old pool served as a bulkhead.
- [ ] Appropriate DB pool, HTTP pool, rate limits, and timeouts are in place.
- [ ] Virtual threads are not used as a solution to raise CPU-bound throughput.
- [ ] Server request execution and event-loop architectures have been checked separately.
- [ ] Daemon virtual threads/`spring.main.keep-alive` have been checked for background-only apps.
- [ ] Pinning and actual I/O performance have been tested when needed.
- [ ] Startup, throughput, P95/P99, heap, errors, and rejected/blocked tasks have been measured.
- [ ] Load tests have been run with production-like downstream constraints.
- [ ] Shutdown with in-flight tasks has been tested and cleanup confirmed.
- [ ] Clear documentation explains where new limits live at specific executors/resources.

## 28. Summary

1. **Virtual threads do not use a fixed-size worker pool model for Spring Boot 3.3's auto-configured task executor/scheduler.** When enabling `spring.threads.virtual.enabled=true` on Java 21+, Boot switches the executor to `SimpleAsyncTaskExecutor` and the scheduler to `SimpleAsyncTaskScheduler` in corresponding auto-config scenarios.
2. Consequently, **`spring.task.execution.pool.core-size`, `max-size`, `queue-capacity`, `keep-alive`, and `spring.task.scheduling.pool.size` no longer take effect on those auto-configured simple components**.
3. **`spring.task.execution.simple.concurrency-limit` and `spring.task.scheduling.simple.concurrency-limit`** are options for corresponding concurrency limits, yet are **not equivalent** to old pool size/queue-capacity and do not limit the entire JVM.
4. **Custom platform-thread pools, JDBC/HTTP connection pools, Reactor Netty event loops, and downstream rate limits remain independent.** The global virtual flag does not eliminate all tuning needs.
5. **Virtual threads fit best with many blocking I/O tasks**, and do not make CPUs or external resources infinite. Resource-based limits, backpressure, timeouts, and metric tracking remain required.
6. **`SimpleAsyncTaskScheduler` has a specific caveat for fixed-delay**, whereas fixed-rate/cron fit the virtual-thread-per-task model better; change trigger types only after evaluating business semantics.
7. **Measure the actual implementation and execution threads**, not just the properties file. A successful migration means the system maintains proper throughput, latency, error handling, and downstream safety under real load.

### Official documentation

- [Spring Boot 3.3 — Virtual Threads](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): how to enable, daemon/keep-alive characteristics, and caveats.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): selecting `SimpleAsyncTaskExecutor` / `SimpleAsyncTaskScheduler` when virtual threads are enabled.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.task.execution.pool.*`, `spring.task.execution.simple.concurrency-limit`, `spring.task.scheduling.pool.size`, and simple scheduler concurrency.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executor/scheduler implementations and fixed-delay caveat with `SimpleAsyncTaskScheduler`.
- [Spring Framework 6.1 — SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html): scheduler thread, fixed-delay, and concurrency limit.
- [Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual threads model, usage recommendations, and relationship with blocking operations.
