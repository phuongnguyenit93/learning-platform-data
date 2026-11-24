# Components Using an Executor or Scheduler When Virtual Threads Are Enabled in Spring Boot

When running Spring Boot on **Java 21+**, you can enable virtual threads via the configuration `spring.threads.virtual.enabled=true`. This change does not mean **every** operation in the application suddenly runs on a virtual thread. It causes Spring Boot to **adjust certain auto-configured components**, especially the **task executor** and **task scheduler**. Only components that actually use those resources exhibit the corresponding behavior.

Two ideas to grasp first:

- **Executor** answers *where will the task be executed?* For example, an `@Async` call can be submitted to an `AsyncTaskExecutor`.
- **Scheduler** answers *when should the task be triggered?* For example, `@Scheduled` is registered with a `TaskScheduler`, which then runs the work on schedule.

When virtual threads are enabled, Spring Boot 3.3 can auto-create a **`SimpleAsyncTaskExecutor` using virtual threads** and a **`SimpleAsyncTaskScheduler` using virtual threads** instead of the usual default thread pools. However, actual behavior still depends on **Java version, auto-configuration conditions, application-defined beans, trigger types, and how the method is called**.

This lesson uses **Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 21**. Sections mentioning Java 17 are only for comparison when virtual threads *cannot yet be enabled*.

## 1. What does a virtual thread actually change?

Virtual threads are an official Java 21 feature (JEP 444). A virtual thread is a `java.lang.Thread` that is lighter than a platform thread in many situations, especially for blocking I/O code following a thread-per-task model.

Standalone example independent of Spring, running on Java 21:

~~~java
public class VirtualThreadBasics {
    public static void main(String[] args) throws Exception {
        Thread task = Thread.ofVirtual()
                .name("sample-vt")
                .start(() -> {
                    System.out.println(
                            "inside virtual = "
                                    + Thread.currentThread().isVirtual());
                });
        task.join();

        System.out.println(
                "main virtual = "
                        + Thread.currentThread().isVirtual());
    }
}
~~~

Compile and run in the directory containing `VirtualThreadBasics.java`:

~~~bash
javac VirtualThreadBasics.java
java VirtualThreadBasics
~~~

Output:

~~~text
inside virtual = true
main virtual = false
~~~

Virtual threads do not eliminate the need for CPU, memory, sockets, database pools, or connection limits. They are particularly useful for reducing the cost of holding **very many tasks waiting on I/O** compared to each task occupying a more expensive platform thread.

**Do not interpret this as “virtual thread = faster for every task”.** A CPU-bound task still requires real CPU; virtual threads do not increase CPU core count. With upstream limits, many virtual threads can even generate more concurrent calls than dependencies can handle.

In Java 21, there are cases where a virtual thread gets **pinned** to its carrier thread when blocking inside a `synchronized` block or native code. That can reduce scalability. Therefore, measure real workloads rather than changing production configuration based solely on how many threads can be created.

## 2. How to enable in Spring Boot

With Spring Boot 3.3 on Java 21+, put in `src/main/resources/application.properties`:

~~~properties
spring.threads.virtual.enabled=true
~~~

Or in `application.yml`:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

This configuration takes effect when **the actual runtime is Java 21+**. If the application still runs on Java 17, you cannot use JDK virtual threads simply by changing a property; upgrade the compatible runtime/JDK first.

To verify the Java version:

~~~bash
java -version
~~~

Additionally, inside a Java 21 program you can check:

~~~java
System.out.println(Thread.currentThread().isVirtual());
~~~

If the line above prints `false` in `main`, it does **not** mean the feature is disabled: `main` normally runs on a platform thread; only tasks submitted to an executor/scheduler with virtual-thread support need to run on virtual threads.

### Comparing the two configuration modes

| Aspect | Virtual threads disabled, typically | `spring.threads.virtual.enabled=true` on Java 21+ |
|---|---|---|
| Boot auto-configured Executor | Typically `ThreadPoolTaskExecutor` | Typically `SimpleAsyncTaskExecutor` creating a virtual thread per task |
| Boot auto-configured Scheduler | Typically `ThreadPoolTaskScheduler` | Typically `SimpleAsyncTaskScheduler` supporting virtual threads |
| Valid `@Async` using default executor | Typically runs on platform worker pool | Can run on virtual threads created by Boot's executor |
| `@Scheduled` using default scheduler | Typically uses a scheduled platform thread pool | Can run on virtual threads, **depending on trigger type** |
| A manually declared `ThreadPoolTaskExecutor` | Still follows that bean's own configuration | **Does not automatically become** a virtual-thread executor |
| A manually declared `ThreadPoolTaskScheduler` | Still follows that bean's own configuration | **Does not automatically become** a virtual-thread scheduler |
| Thread name / pool size | Depends on configured pool | Do not assume the same pool mechanics apply |
| JVM liveness | Depends on non-daemon threads and other components | Virtual threads are daemon; keep-alive must be considered |

The table describes **typical auto-configuration conditions**, not a guarantee that any application with arbitrary dependencies/custom beans receives those exact two implementations.

## 3. Which components use an executor?

An executor is where a `Runnable` or `Callable` runs. In the Spring ecosystem, you may encounter:

- `java.util.concurrent.Executor`: JDK contract for running tasks.
- `org.springframework.core.task.TaskExecutor`: Spring's task execution abstraction.
- `org.springframework.core.task.AsyncTaskExecutor`: extension for submitting asynchronous tasks.
- `ThreadPoolTaskExecutor`: Spring adapter for a platform-thread pool with core/max/queue configuration.
- `SimpleAsyncTaskExecutor`: creates a new thread per task, capable of using **virtual threads** in Spring Framework 6.1+.

In Boot's default configuration when conditions are met, the task executor bean is named **`applicationTaskExecutor`**. It can be used by task execution integration points such as:

1. **`@Async`** when `@EnableAsync` is enabled and executor resolution is not overridden.
2. **Spring MVC asynchronous request processing** when a suitable executor type/name is recognized by MVC configuration.
3. **Certain framework components or application code** that explicitly inject that `AsyncTaskExecutor` / `TaskExecutor`.
4. **Task submission calls written by the application itself** when using the selected executor bean.

Do not generalize that all HTTP requests, all Reactor/WebFlux event-loop tasks, every `CompletableFuture.supplyAsync(...)`, or every third-party library automatically switch to Boot's executor:

- `CompletableFuture.supplyAsync(...)` **without passing an Executor** usually uses the common ForkJoinPool, not `applicationTaskExecutor` by default.
- `new Thread(...)` creates a platform thread unless you explicitly choose the virtual thread API.
- A library with its own executor will keep using that executor unless configured otherwise.
- Embedded server request processing threads are a **separate** container configuration topic, not to be equated with Spring MVC using `applicationTaskExecutor` for asynchronous MVC processing.
- Reactive event loops are a different execution mechanism; enabling the virtual threads property does not turn every event loop into virtual threads.

**To know where a component actually runs, inspect the injected executor and `Thread.currentThread().isVirtual()` inside the task.**

## 4. @Async, @EnableAsync, and virtual-thread executor

Example:

~~~java
@Service
public class MailJob {

    @Async
    public CompletableFuture<String> send(String message) {
        // When the proxy handles @Async, the method is submitted to the executor.
        return CompletableFuture.completedFuture("sent:" + message);
    }
}
~~~

This is an **illustrative** snippet requiring imports for `Service`, `Async`, `CompletableFuture`, and `@EnableAsync` enabled in Spring configuration.

Conditions to understand clearly:

1. `@EnableAsync` activates `@Async` processing infrastructure.
2. The caller must invoke the method **through a valid Spring proxy**. `this.send(...)` called from inside the same regular bean is **not** intercepted by `@Async` in default proxy mode.
3. The system must resolve an executor: via `@Async("beanName")`, `AsyncConfigurer`, a dedicated bean, or the configured default executor.
4. If the selected executor is `SimpleAsyncTaskExecutor` with virtual threads enabled, the method can run on a virtual thread.
5. If the selected executor is a platform-thread `ThreadPoolTaskExecutor` you defined yourself, the method still runs on a platform thread even when the virtual property is on.

Example explicitly selecting Boot's auto-configured bean (if that bean exists):

~~~java
@Async("applicationTaskExecutor")
public CompletableFuture<Boolean> inspect() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().isVirtual());
}
~~~

This is an illustrative method inside a Spring bean, not a standalone program. This approach is helpful when you need to know the exact executor being used. However, it also creates a dependency on the **bean name**; in an application with custom configuration, verify whether the bean is still created or has been replaced by another bean.

### SimpleAsyncTaskExecutor is not a fixed pool

When using virtual threads, `SimpleAsyncTaskExecutor` follows a model of creating **a new thread for each task** rather than “borrowing a worker” from a fixed platform-thread pool:

~~~text
Task 1 --> virtual thread 1
Task 2 --> virtual thread 2
Task 3 --> virtual thread 3
...
~~~

Hence `core-size`, `max-size`, and `queue-capacity` are parameters **belonging to the thread pool model**, and do not carry the same meaning on `SimpleAsyncTaskExecutor`.

Do not set `spring.task.execution.pool.max-size=500` and conclude “the maximum number of virtual threads is 500”. When Boot uses SimpleAsyncTaskExecutor, pool-related properties do not control this bean type the way they apply to ThreadPoolTaskExecutor.

If concurrency limiting is required, a separate policy is needed: `SimpleAsyncTaskExecutor` has `setConcurrencyLimit(...)`, or you use a semaphore/rate limiter, a backpressure-aware queue, or a quota aligned with downstream capacity. An executor-level concurrency limit alone is not enough to manage total cluster traffic.

## 5. Which components use a scheduler?

Spring scheduling involves:

- `org.springframework.scheduling.TaskScheduler`: interface for scheduling tasks.
- `ThreadPoolTaskScheduler`: uses a standard scheduled platform thread pool.
- `SimpleAsyncTaskScheduler`: a scheduler optimized for thread-per-task, suited for virtual threads.
- `ScheduledAnnotationBeanPostProcessor`: infrastructure registering `@Scheduled` methods when `@EnableScheduling` is enabled.

A method:

~~~java
@Scheduled(fixedRate = 10_000)
public void poll() {
    // Triggered on a schedule, not automatically invoked via @Async.
}
~~~

This is an illustrative method inside a Spring bean. Without enabling scheduling, merely placing the annotation does not guarantee triggering.

When Boot auto-configures the default scheduler and virtual threads are enabled, the implementation is typically `SimpleAsyncTaskScheduler`. The scheduler still **computes and tracks schedules**, while dispatching executions onto virtual threads.

### Special note: fixedDelay differs from fixedRate/cron

With `SimpleAsyncTaskScheduler`:

- **fixed-rate** and **cron** triggers are designed favorably for running tasks on new threads, which can be virtual threads when the feature is enabled.
- **fixed-delay** tasks behave differently: they execute on **a single scheduler thread**, to preserve the semantics of delaying *after the previous execution completes*.
- Therefore, **do not blanket-claim “every @Scheduled method is a virtual thread”** when enabling the property.

Spring Framework 6.1 recommends paying special attention to using `fixedDelay` with `SimpleAsyncTaskScheduler`. A long-running fixed-delay task can occupy the scheduler thread and delay other fixed-delay tasks or schedules. If the workload fits, consider fixed-rate/cron with overlap limits or decouple triggering from worker execution.

Comparison:

| Trigger | Schedule meaning | What to watch out for in SimpleAsyncTaskScheduler |
|---|---|---|
| `@Scheduled(fixedRate=...)` | Interval between scheduled start times | Can dispatch task on virtual thread; must handle overlapping tasks. |
| `@Scheduled(cron="...")` | Fires according to cron schedule | Can dispatch task on virtual thread; must consider timezone and multiple replicas. |
| `@Scheduled(fixedDelay=...)` | Waits an interval after previous run finishes | Runs on a single scheduler thread; should not block too long. |
| `@Scheduled(initialDelay=...)` | Waits before first trigger | Only a timing option; does not determine thread type. |

**Do not choose fixed-rate solely to “force a virtual thread”.** If each tick spawns long-running work that may overlap, you must add idempotency, concurrency caps, timeouts, backpressure, and overload handling policies.

## 6. Runnable Java 21 + Spring Boot 3.3 example that self-inspects thread types

This example does not manually declare an `Executor` or `TaskScheduler`, so **Spring Boot auto-configuration** can pick the appropriate implementations when the virtual threads property is enabled.

Verification goals:

1. `applicationTaskExecutor` is `SimpleAsyncTaskExecutor`.
2. `taskScheduler` is `SimpleAsyncTaskScheduler`.
3. An `@Async` method runs on a virtual thread.
4. A `@Scheduled(fixedRate=...)` trigger runs on a virtual thread.
5. A `@Scheduled(fixedDelay=...)` trigger demonstrates running on the scheduler thread.

To avoid the mistake of `main()` exiting prematurely because virtual threads are daemon threads, `ApplicationRunner` waits for all three probe signals to complete before allowing the context to close.

### Project structure

~~~text
virtual-task-demo/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/virtualtasks/VirtualTaskApplication.java
        └── resources/application.properties
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.virtualtasks.VirtualTaskApplication'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=virtual-task-demo
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
logging.level.root=INFO
~~~

`spring.main.keep-alive=true` is not strictly required to run this demo program properly because the runner waits on the platform main thread; the property is included to illustrate how to configure background applications that must remain alive when most work runs on daemon virtual threads. The lesson explains this in more detail later.

File `src/main/java/com/example/virtualtasks/VirtualTaskApplication.java`:

~~~java
package com.example.virtualtasks;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class VirtualTaskApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(VirtualTaskApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // The runner has waited for the three tasks to complete.
        }
    }

    @Bean
    ProbeSignals probeSignals() {
        return new ProbeSignals();
    }

    @Bean
    AsyncWorker asyncWorker(ProbeSignals signals) {
        return new AsyncWorker(signals);
    }

    @Bean
    TickSources tickSources(AsyncWorker worker, ProbeSignals signals) {
        return new TickSources(worker, signals);
    }

    @Bean
    ApplicationRunner report(
            ProbeSignals signals, ApplicationContext context) {
        return args -> {
            if (!signals.completed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for scheduled/async work");
            }

            Object executor =
                    context.getBean("applicationTaskExecutor");
            Object scheduler =
                    context.getBean("taskScheduler");

            System.out.println(
                    "Executor type = "
                            + executor.getClass().getSimpleName());
            System.out.println(
                    "Scheduler type = "
                            + scheduler.getClass().getSimpleName());
            System.out.println(
                    "@Async virtual = " + signals.asyncVirtual.get());
            System.out.println(
                    "fixedRate virtual = " + signals.rateVirtual.get());
            System.out.println(
                    "fixedDelay virtual = " + signals.delayVirtual.get());
        };
    }

    public static final class ProbeSignals {
        final CountDownLatch completed = new CountDownLatch(3);
        final AtomicReference<Boolean> asyncVirtual =
                new AtomicReference<>();
        final AtomicReference<Boolean> rateVirtual =
                new AtomicReference<>();
        final AtomicReference<Boolean> delayVirtual =
                new AtomicReference<>();
    }

    public static class AsyncWorker {
        private final ProbeSignals signals;

        public AsyncWorker(ProbeSignals signals) {
            this.signals = signals;
        }

        @Async("applicationTaskExecutor")
        public void doWork() {
            signals.asyncVirtual.set(
                    Thread.currentThread().isVirtual());
            signals.completed.countDown();
        }
    }

    public static class TickSources {
        private final AsyncWorker worker;
        private final ProbeSignals signals;

        public TickSources(AsyncWorker worker, ProbeSignals signals) {
            this.worker = worker;
            this.signals = signals;
        }

        @Scheduled(initialDelay = 250, fixedRate = 60000)
        public void fixedRateTick() {
            signals.rateVirtual.set(
                    Thread.currentThread().isVirtual());
            signals.completed.countDown();

            // Goes through the Spring proxy of the separate AsyncWorker bean.
            worker.doWork();
        }

        @Scheduled(initialDelay = 250, fixedDelay = 60000)
        public void fixedDelayTick() {
            signals.delayVirtual.set(
                    Thread.currentThread().isVirtual());
            signals.completed.countDown();
        }
    }
}
~~~

**Why two separate beans?** `TickSources` calls `AsyncWorker.doWork()` through a Spring-proxied bean. If `doWork()` were in the same class and called via `this.doWork()`, the default proxy-mode `@Async` mechanism might not run; then the thread switch the example aims to verify would not occur.

**Why use CountDownLatch(3)?** The runner does not need to guess scheduling timing. Two triggers and one async task each signal completion once. Once the latch reaches 0, the thread type values have already been written, so the runner can read them safely.

**Why not declare custom executor/scheduler beans?** When the project has no beans that make Boot task execution/scheduling auto-configuration back off, auto-configuration can choose the implementations using virtual threads. If you add a custom executor to the example, the output will no longer reflect this default path.

### How to run

Install JDK 21 and use a Gradle version compatible with Java 21. In the project directory containing the Gradle wrapper, run:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If you need to change the JDK for Gradle, the Java toolchain configuration in the example requires a JDK 21 that Gradle can discover. Running `javac VirtualTaskApplication.java` alone is not enough because the code depends on Spring Boot and Spring Framework on the classpath.

Ignoring Spring Boot/Gradle logs, **the program's stdout under the described auto-configuration conditions** is:

~~~text
Executor type = SimpleAsyncTaskExecutor
Scheduler type = SimpleAsyncTaskScheduler
@Async virtual = true
fixedRate virtual = true
fixedDelay virtual = false
~~~

The order of the five lines is deterministic because they are printed sequentially inside the runner **after** all three signals finish. The actual start order of the two scheduled methods does not need to be fixed; the latch removes any dependency on that ordering. If the output differs, first check the Java/Boot versions, whether the property actually took effect, the `applicationTaskExecutor` and `taskScheduler` beans, custom beans, or proxy configuration in the project.

Note: the line `fixedDelay virtual = false` describes the behavior of `SimpleAsyncTaskScheduler` in Spring Framework 6.1, where fixed-delay tasks execute on the regular scheduler thread. It is not a claim that every TaskScheduler or every JDK version always runs fixed-delay on a platform thread.

## 7. When adding a custom Executor, what happens?

A real-world application often already has thread pools for handling emails, reports, messages, or tasks with different priorities.

Illustrative example **changing behavior compared to section 6's program**:

~~~java
@Bean("reportExecutor")
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("report-platform-");
    return executor;
}
~~~

This snippet requires importing `ThreadPoolTaskExecutor` and placing it in a configuration class with `@Bean`. When a custom `Executor` bean appears, Boot's auto-configuration conditions may **no longer create** the default executor as before. If a method is annotated:

~~~java
@Async("reportExecutor")
public void generateReport() {
    System.out.println(Thread.currentThread().isVirtual());
}
~~~

it uses the exact `reportExecutor` bean you selected. With the platform-thread `ThreadPoolTaskExecutor` above, `isVirtual()` is `false` even though `spring.threads.virtual.enabled=true`.

**Do not call this code a “standalone example”**: it is two illustrative config/method snippets that must be placed in Spring beans with `@EnableAsync` and proper imports.

To keep automatic virtual threads for one group of tasks while maintaining a dedicated platform pool for another, **create explicit beans, select executors by qualifier, and verify auto-config conditions**. Do not assume Boot will still create `applicationTaskExecutor` if another `Executor` already exists; inspect the actual beans in the context.

A custom `SimpleAsyncTaskExecutor` can be configured to support virtual threads:

~~~java
@Bean("virtualReportExecutor")
SimpleAsyncTaskExecutor virtualReportExecutor() {
    SimpleAsyncTaskExecutor executor =
            new SimpleAsyncTaskExecutor("report-vt-");
    executor.setVirtualThreads(true);
    executor.setConcurrencyLimit(100);
    return executor;
}
~~~

This snippet is also additional configuration requiring importing `SimpleAsyncTaskExecutor` and a Spring configuration class. `setConcurrencyLimit(100)` expresses the need to bound **concurrent work**, rather than creating a pool of 100 platform workers. When declaring a bean yourself, you also need to check lifecycle/shutdown and how Spring manages your executor.

**A practical rule:** do not implicitly mix the request executor, batch executor, and event handler executor. Select by name, apply separate metrics/timeouts/quotas, and enable virtual threads only for verified workloads.

## 8. When adding a custom TaskScheduler, what happens?

A project may want scheduled jobs to use a dedicated scheduler:

~~~java
@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-platform-");
    return scheduler;
}
~~~

This is an illustrative method requiring importing `ThreadPoolTaskScheduler`. Once an application-declared scheduler bean exists, Spring Boot can **back off** creating the default scheduler that uses virtual threads.

Consequence: `@Scheduled` using the custom scheduler above will still run on regular **platform threads**, unless your configuration explicitly selects another implementation. Enabling a general property **does not change the class of an object you constructed in Java**.

If you need to actively use a virtual-thread scheduler, you can instantiate `SimpleAsyncTaskScheduler` yourself, enable virtual threads, and manage its lifecycle accordingly. However, if Boot already provides suitable configuration, starting with **auto-configuration** is usually safer and less complex.

### Pool properties no longer carry the same meaning

In platform-thread mode, you might use:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.scheduling.pool.size=4
~~~

These properties primarily target thread-pool-based implementations. When Boot chooses `SimpleAsyncTaskExecutor` and `SimpleAsyncTaskScheduler` for virtual threads, **do not expect** `pool.max-size` or `pool.size` to impose a corresponding virtual-thread concurrency limit. And if you constructed the executor/scheduler yourself with `new`, these auto-configuration properties are not automatically bound to your bean either.

Check the **actual bean type**, concurrency policy, and metrics instead of reading configuration and inferring without verification.

## 9. Web MVC, HTTP server, and reactive runtime: avoid overgeneralizing

Virtual threads are integrated by Boot at multiple points, yet **request processing paths** do not always pass through the same bean:

| Scenario | What to verify |
|---|---|
| `@Async` on a service | Does the proxy run? Which executor is selected? |
| Spring MVC asynchronous request processing | Does MVC use the matching `applicationTaskExecutor`? |
| Normal HTTP requests via embedded servlet container | Which executor/request thread model does the current container version use? |
| WebFlux/Reactor event loop | Is Reactor's scheduler/event loop being replaced? Do not assume yes by default. |
| `CompletableFuture.supplyAsync(...)` without passing an executor | Typically uses common ForkJoinPool, not Spring's executor automatically. |
| `@Scheduled` | Which TaskScheduler is selected, and is the trigger fixed-rate, fixed-delay, or cron? |
| Kafka/Rabbit/Quartz or other client libraries | Do they have their own executor/scheduler? Do not assume all use virtual threads. |

An HTTP request running on a platform thread **can still call** an `@Async` service routed to virtual threads. Conversely, an HTTP server may use the container's own virtual-thread support while a custom `ThreadPoolTaskExecutor` in a service still uses platform threads. There is no contradiction here: **each component has its own execution resources**.

To accurately evaluate HTTP server capabilities, examine the corresponding container configuration and Spring Boot version. This lesson does not treat enabling virtual threads for `applicationTaskExecutor` as proof that all request handling changes thread type.

## 10. Virtual threads do not automatically solve downstream blocking

Virtual threads reduce one kind of waiting overhead, yet they **do not** make dependencies infinite.

Suppose a service has 10,000 virtual threads calling a database that only allows a pool of 50 connections. In practice, the maximum number of connections provided by the pool remains a finite resource. Many tasks will wait, time out, or be rejected.

Limits that must be managed:

- **Database pool:** connection count, wait queue, timeouts, transaction duration.
- **HTTP client:** max connections/streams, upstream rate limits, timeouts, retries.
- **CPU:** heavy computational tasks still contend for CPU cores.
- **Memory:** tasks, stack state, and data held in virtual threads still consume heap/native resources.
- **Remote API:** you cannot send more requests than the quota and expect zero errors.
- **Scheduler:** too many scheduled tasks or blocking fixed-delay methods can still cause delays.
- **Downstream systems:** a burst of tasks waking up simultaneously can cause a “thundering herd”.

Therefore, when adopting virtual threads, you still must design **backpressure**:

~~~text
Request / scheduler tick
        |
        v
Admission limit (semaphore / rate limiter / bounded queue)
        |
        v
Virtual-thread executor
        |
        v
Client / connection pool / dependency
        |
        v
Timeout, controlled retry, circuit breaker, metrics
~~~

Do not push every task into an unbounded queue and just raise the number of virtual threads. For work that must survive restarts, you need a durable queue or separate job storage, not just an in-memory executor.

## 11. Virtual threads and synchronized, pinning in Java 21

Virtual threads prevent Java code's I/O waiting from **occupying a carrier thread** in many cases. However, in Java 21, a virtual thread can get **pinned** when blocking inside a `synchronized` monitor block or certain native/foreign operations. The carrier platform thread may then be held while the virtual thread waits.

Example of an anti-pattern to reflect on:

~~~java
synchronized (lock) {
    // An I/O call that may block for a long time.
    remoteClient.call();
}
~~~

This is **illustrative code** with pre-existing `lock` and `remoteClient` variables, not a standalone program. When running in a virtual thread on Java 21, a synchronized section combined with prolonged blocking I/O can significantly degrade virtual thread effectiveness.

Ways to improve:

1. Keep `synchronized` blocks small and free of blocking I/O.
2. Use an appropriate concurrency primitive if a different synchronization construct is needed; do not replace arbitrarily without verifying semantics.
3. Set timeouts on I/O and bound concurrent work.
4. Use Java Flight Recorder / pinning observation as supported by the running JDK/runtime.
5. Measure throughput, latency, and carrier-thread usage before and after switching.

Do not confuse pinning with deadlock: a pinned task is **not necessarily** deadlocked, yet it can make carrier threads scarce under high load. Pinning handling differs across JDK versions; the focus here is Java 21.

## 12. ThreadLocal, MDC, transaction, and security context

A virtual thread is still a `Thread`, so the `ThreadLocal` API exists and works on virtual threads. However, that **does not mean the caller's thread-bound state automatically carries over to a new task**.

| Topic | What to clarify |
|---|---|
| `ThreadLocal` | Exists on virtual threads, yet state lives per thread; not automatically shared with the caller. |
| MDC/log correlation | Requires context propagation or an appropriate `TaskDecorator` if correlation must cross threads. |
| Spring SecurityContext | Verify and configure propagation per framework; do not assume the worker has the request thread's privileges. |
| Spring transaction | Transactions are bound to the call's execution context/thread; `@Async` does not automatically carry the caller's open transaction to the worker. |
| Request attributes | May no longer exist when the task runs later than the request or outside MVC context. |
| Caching and mutable state | Many concurrent tasks can cause races; virtual threads do not add thread-safety automatically. |

For example, a `@Transactional` method calls `@Async`. The worker may run on a virtual thread **different from the transaction thread**. Do not assume by default that the worker shares that transaction. If the task needs its own transaction, design the transaction boundary on the service invoked through an appropriate proxy.

Similarly, an HTTP request timing out or expiring does not automatically cancel all virtual-thread tasks it submitted. You need cancellation, timeouts, tracing, and ownership of background work.

## 13. Virtual threads are daemon: why is keep-alive needed?

Java virtual threads are **daemon threads**. The JVM does not necessarily keep the process alive simply because virtual threads are still running. This is especially important for Spring Boot applications **without a web server or non-daemon component keeping the JVM alive**, having only a scheduler/executor using virtual threads.

Spring Boot provides:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

When `spring.main.keep-alive=true`, Spring Boot keeps the application alive appropriately in virtual threads mode even when no platform non-daemon threads created by other components remain. For a console batch program that only needs to finish one job and exit, keeping the process alive indefinitely may **not** be the goal.

Remember to distinguish:

- **Server/web app:** the request listener/server may keep the process alive in its own way; still verify actual operational behavior.
- **Background-only app:** if only the virtual-thread scheduler remains, consider how to keep the JVM alive.
- **Batch app:** if the goal is to finish the job and exit, await completion with a timeout and close the context; do not enable keep-alive unconditionally.

The example in section 6 intentionally waits using `CountDownLatch` and closes the context upon completion to demonstrate an explicit termination condition. In production, shutdown must be designed intentionally rather than relying on the accidental presence or absence of non-daemon threads.

## 14. Shutdown and lifecycle of executor/scheduler

Enabling virtual threads **does not** eliminate the need to stop tasks cleanly:

1. Stop accepting new tasks.
2. Stop scheduled triggers or cancel corresponding schedules.
3. Give running tasks time to finish or request cancellation/interruption.
4. Release connections/clients/resources.
5. Close the context and respect the platform's timeout/grace period.

A task submitted to `SimpleAsyncTaskExecutor` creating a new virtual thread is not like a `ThreadPoolTaskExecutor` queue. Therefore, you cannot rely unchanged on assumptions like “8-thread worker pool, 100-task queue” to predict shutdown.

`ThreadPoolTaskScheduler` and `SimpleAsyncTaskScheduler` also do not share the same internal structure. For fixed-delay tasks, consider long-running callbacks on the scheduler thread. For fixed-rate/cron tasks, handle overlap/cancellation according to business contracts.

If the application needs a job **guaranteed to run even across Pod restarts**, an in-JVM task executor/scheduler does not replace a message broker, durable scheduler, or transaction log. You must clearly define storage, retries, idempotency, and work ownership assignment.

## 15. When to prefer virtual threads and when to keep a platform pool?

| Workload characteristic | Consideration |
|---|---|
| Many requests/tasks waiting on blocking I/O, with clear downstream limits | Virtual threads are usually worth testing. |
| Heavy, sustained CPU-bound work | Virtual threads do not add CPU; cap concurrency by cores. |
| I/O tasks using heavy synchronized blocking on Java 21 | Measure pinning and consider refactoring before switching. |
| Long fixed-delay schedules needing to avoid holding scheduler thread | Consider another scheduler, suitable fixed-rate/cron, or controlled offload. |
| Tasks needing a bounded pool with strict queue/rejection policies | A platform thread pool or custom-designed executor may be easier to control. |
| Short tasks needing stable throughput and minimal overhead | Benchmark; virtual threads do not necessarily win every time. |
| Client/downstream already has a very small concurrency limit | Virtual threads do not increase downstream capacity. |
| Application has custom executors/schedulers in many places | Evaluate and migrate **bean by bean**; the global property is not enough. |

A safe rollout path:

1. Upgrade JDK to Java 21+ and stay on a supported Spring Boot version.
2. Enable `spring.threads.virtual.enabled=true` in a test environment.
3. Inspect bean types/thread dumps and confirm each workload actually uses virtual threads.
4. Measure throughput, p95/p99 latency, CPU, heap, GC, downstream connection pools, retries, and pinning.
5. Set appropriate concurrency/rate limits.
6. Test stop/restart/shutdown, cancellation, and tracing.
7. Roll out broadly only after verifying real benefits and risks.

## 16. Common mistakes

**Mistake 1 — “Enabling one property makes every Java thread in the process a virtual thread.”**

False. It changes Boot-supported integrations; `main`, custom thread pools, event loops, and many libraries can still use platform threads.

**Mistake 2 — “@Async definitely runs on a virtual thread when the property is enabled.”**

Not guaranteed. You must enable `@EnableAsync`, call through a Spring proxy, and select the right executor. A custom `ThreadPoolTaskExecutor` still creates platform workers.

**Mistake 3 — “Every @Scheduled runs on a virtual thread.”**

False with default `SimpleAsyncTaskScheduler` on Java 21: fixed-delay tasks run on **the scheduler thread**. Check the trigger type.

**Mistake 4 — “Configuring pool.max-size limits virtual threads.”**

Not with `SimpleAsyncTaskExecutor`. Pool properties belong to the pool model; you need proper concurrency limits/backpressure.

**Mistake 5 — “Using CompletableFuture.supplyAsync without an executor picks Boot's applicationTaskExecutor.”**

Not by default. It usually picks the JDK common pool. To use Spring's executor, explicitly pass a compatible executor.

**Mistake 6 — “Putting @Async in the same class and calling this.method() switches threads.”**

Not in regular proxy mode; self-invocation bypasses the interceptor.

**Mistake 7 — “Virtual threads have no ThreadLocal.”**

False. ThreadLocal exists; the issue is cost and propagation of thread-bound state between caller and worker.

**Mistake 8 — “Virtual threads make DB connections and CPU infinite.”**

False. Downstream resources remain finite; excessive concurrency can cause worse overload than before.

**Mistake 9 — “A scheduler-only app will stay alive forever because virtual threads remain.”**

Not guaranteed because virtual threads are daemon threads. Consider `spring.main.keep-alive` or an explicit await strategy.

**Mistake 10 — “spring.threads.virtual.enabled automatically converts executor/scheduler beans I wrote.”**

No. A `new ThreadPoolTaskExecutor()` object stays that type until you explicitly replace it.

**Mistake 11 — “Virtual threads solve all synchronized blocking situations.”**

Not in Java 21; pinning can reduce scalability. Observe and fix blocking in critical sections where appropriate.

**Mistake 12 — “A @Scheduled cron runs only once in a Kubernetes cluster.”**

No. Each replica can have its own scheduler. If a job requires single execution cluster-wide, design leader election/distributed locking, durable job state, and idempotency.

## 17. Self-verification exercises

Based on the example in section 6, try sequentially:

1. **Disable `spring.threads.virtual.enabled`** and observe bean types/thread data change to Spring Boot 3.3's platform-thread defaults.
2. **Enable only virtual threads** and verify `@Async virtual=true`, `fixedRate virtual=true`, `fixedDelay virtual=false` under the demo conditions.
3. **Add a custom `ThreadPoolTaskExecutor` named `applicationTaskExecutor`**, then check whether `@Async` still uses virtual threads. Watch auto-config conditions and avoid duplicate bean declarations.
4. **Add a custom `ThreadPoolTaskScheduler` named `taskScheduler`** to compare thread types of scheduled methods. Perform this in a separate run without overlapping two beans of the same name.
5. **Remove `@EnableAsync`** and see whether the worker call still goes through the async interceptor.
6. **Remove `@EnableScheduling`** and observe the runner time out due to missing triggers, thereby understanding the role of scheduling infrastructure.
7. **Add blocking I/O with a timeout** inside the worker, then measure concurrency and response time; do not run unbounded load.
8. **Try a long fixed-delay method** on the virtual-aware scheduler and observe delays on other schedules.
9. **Test a non-web app without keep-alive**, comparing JVM termination against a version with `spring.main.keep-alive=true`; remember to control and stop the process during testing.
10. **Run multiple replicas in staging**, checking whether the scheduled job executes redundantly on each instance.

Quick check snippet in code:

~~~java
System.out.println(
        "Thread = " + Thread.currentThread().getName()
                + ", virtual = "
                + Thread.currentThread().isVirtual());
~~~

This is Java 21 code placed **inside the exact method under test**; if run only in `main()` or outside the proxy, it does not reflect the thread of `@Async`/`@Scheduled`.

### References

- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — SpringApplication and keep-alive: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 — `SimpleAsyncTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html
- Spring Framework 6.1 — `SimpleAsyncTaskScheduler`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html
- OpenJDK — JEP 444 Virtual Threads: https://openjdk.org/jeps/444

**Key takeaway:** `spring.threads.virtual.enabled=true` on Java 21+ allows **components auto-configured by Spring Boot** to use virtual-thread-aware executors and schedulers. `@Async` depends on **the selected executor**; `@Scheduled` depends on **the scheduler and trigger type** (pay special attention to `fixedDelay`). Custom pools, Reactor event loops, libraries with their own executors, and transaction/thread-bound state **do not convert automatically**. Proper operation requires checking actual beans, thread types, concurrency limits, blocking tasks, keep-alive, and shutdown policies.
