# Distinguishing Spring Framework Defaults from Application-Provided Configuration

## 1. The Question to Answer

When building applications with `@Async`, `@Scheduled`, or `TaskExecutor`, you often hear claims like "Spring comes with 8 threads," "the default scheduler has only 1 thread," or "setting `maxPoolSize` to 50 will run 50 tasks." Each statement is true only within **a specific configuration layer and set of conditions**. The single word "Spring" can actually refer to:

1. **Plain Spring Framework:** interfaces, implementation classes, and how executors/schedulers are selected when annotations are enabled.
2. **A class's own initialization defaults:** for example, `new ThreadPoolTaskExecutor()` has initial defaults defined by that class itself.
3. **Spring Boot auto-configuration:** Boot inspects present beans and conditions and may create executors/schedulers with **Boot's** defaults.
4. **Application configuration properties:** `application.properties`/`application.yml`, environment variables, command-line arguments, profiles; these take effect only when a component actually reads/binds them.
5. **Explicit application beans or configuration:** `@Bean`, `AsyncConfigurer`, `SchedulingConfigurer`, `@Async("beanName")`, and setters like `setCorePoolSize`.
6. **Live runtime state:** current threads, active tasks, queue depth, and rejected tasks vary with load, distinct from configured bounds.

Goal of this lesson: identify **who creates the pool**, **who selects the pool**, **which values actually take effect**, and **how to verify** instead of relying on an out-of-context "Spring default" number.

Examples and specific numbers are scoped to **Spring Framework 6.1/6.2, Spring Boot 3.3.x with Java 17 (platform threads)**. When moving to Java 21 virtual threads, Spring Boot 3.4+, Spring Boot 4, or changing integration components, check the documentation for your exact version. Never assume any default stays constant across generations.

## 2. Distinguishing Four Easily Confused Concepts

### 2.1. An Abstraction Does Not Imply a Pool

`org.springframework.core.task.TaskExecutor` defines `execute(Runnable)`. The interface dictates neither creating new threads nor having a queue:

- `SyncTaskExecutor`: runs directly on the **calling thread**; the call blocks until the task completes.
- `SimpleAsyncTaskExecutor`: normally spawns a new thread per execution rather than reusing a thread pool; concurrency limits can be configured.
- `ThreadPoolTaskExecutor`: wraps `ThreadPoolExecutor`, featuring `corePoolSize`, `maxPoolSize`, `queueCapacity`, and a rejection policy.
- `TaskScheduler` handles time-based/periodic scheduling, distinct from an executor's goal of simply "dispatching work." `ThreadPoolTaskScheduler` owns a pool for scheduled tasks.

Thus, an `@Async` call alone does not prove a thread pool is being used. You must know the **concrete implementation** selected.

### 2.2. "Class Defaults" vs. "Auto-Config Defaults" Differ

For example, `new ThreadPoolTaskExecutor()` (properly initialized and lifecycle-managed) has these initial defaults in Spring Framework 6.1:

| Property | Default value of the class itself |
| --- | --- |
| `corePoolSize` | 1 |
| `maxPoolSize` | `Integer.MAX_VALUE` |
| `queueCapacity` | `Integer.MAX_VALUE` (practically unbounded queue) |
| `keepAliveSeconds` | 60 |
| `ThreadPoolTaskScheduler.poolSize` | 1 |

Subtle detail: with a practically unbounded queue, once tasks exceed core, they are normally **queued**; the pool rarely has any reason to scale toward `maxPoolSize`. Raising only `maxPoolSize` while keeping an unbounded queue usually **does not spawn extra workers as expected**. You must design core/max/queue/rejection together from real load.

`ThreadPoolTaskExecutor` is a **Spring Framework class**, yet when Spring Boot creates and configures it, the effective values can differ (such as Boot 3.3's core size of 8). **Same class, not necessarily the same configuration.**

### 2.3. Auto-Configuration Is Conditional

Spring Framework provides the building blocks and fallbacks when annotations are enabled. Spring Boot adds auto-configuration, but only when **auto-configuration conditions match**. When an application declares its own beans, Boot may back off parts of auto-configuration. Never translate "Boot defaults to creating X" into "Boot always creates X in every application context."

### 2.4. Desired Configuration vs. Actual Configuration

Values in properties files may not apply if the application creates custom beans with `new`/`@Bean` without binding Boot builders/properties. Always inspect the **actual bean** and its getters after the context starts, and observe pool/queue metrics under load.

## 3. Plain Spring Framework: Default Selection Rules

### 3.1. `@EnableAsync` and `@Async`

In Spring Framework 6.1/6.2, when `@EnableAsync` is enabled without specifying an executor via `AsyncConfigurer` or an explicit qualifier, default lookup searches for:

1. A **unique `TaskExecutor` bean** in the context.
2. Failing that, an `Executor` bean named **`taskExecutor`**.
3. If no suitable candidate exists, it falls back to **`SimpleAsyncTaskExecutor`** for async calls.

This is the **selection rule when annotation-driven async is active**, not a promise that plain Spring Framework automatically creates an 8-thread `ThreadPoolTaskExecutor`. `SimpleAsyncTaskExecutor` does not reuse pooled workers; consider thread overhead and concurrency limits under heavy load.

You can control routing explicitly:

~~~java
// Snippet inside a Spring-managed service:
@Async("reportExecutor")
public void createReport(String reportId) {
    // Runs on executor bean named reportExecutor if invoked via the Spring proxy.
}
~~~

`@Async("reportExecutor")` targets that bean for that specific method; it does not change the global default for all `@Async` methods. With `@EnableAsync`'s default proxy mode, internal `this.createReport(...)` calls bypass the proxy and skip the interceptor. To set a global default programmatically, implement `AsyncConfigurer#getAsyncExecutor()` and manage the executor lifecycle properly.

**Failure signature:** an app with two `TaskExecutor` beans and no matching bean named `taskExecutor` may not pick the "default" you assumed. Specify explicit qualifiers or configure a clear default instead of relying on bean registration order.

### 3.2. `@EnableScheduling` and `@Scheduled`

When `@EnableScheduling` is enabled, Spring Framework looks for a unique `TaskScheduler`, or a `TaskScheduler` bean named **`taskScheduler`**; it also performs corresponding lookups for `ScheduledExecutorService`. If no candidate is found, the registrar may create a **single-threaded local scheduler**.

This does not mean the Framework registers a `ThreadPoolTaskScheduler` bean by default that the application can fetch via `getBean(ThreadPoolTaskScheduler.class)`. The registrar's internal fallback differs from an application bean you can inject or configure via Boot properties.

Explicit bean example:

~~~java
// Placed inside a @Configuration class.
@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(3);
    scheduler.setThreadNamePrefix("periodic-");
    return scheduler;
}
~~~

When Spring manages the bean, it handles lifecycle/initialization properly. If created manually outside a Spring context, you must initialize and close the executor yourself. For `@Scheduled(fixedDelay = ...)`, the next run is scheduled after the previous run finishes; for `fixedRate` and cron, timing also depends on the chosen scheduler and load.

### 3.3. Without Enabling Annotations, Annotation Behavior Is Inactive

- `@EnableAsync` enables Spring to intercept `@Async` calls via the registered mechanism.
- `@EnableScheduling` enables Spring to register `@Scheduled` methods.
- Starting Spring Boot or having a `TaskExecutor` bean **does not automatically mean** all `@Async`/`@Scheduled` methods are active. Verify annotations and the live application context.

## 4. Spring Boot 3.3.x: A Different Default Layer

With Java 17 and virtual threads **disabled**, Spring Boot 3.3 documentation describes:

| Case | Typical default when auto-config conditions match |
| --- | --- |
| No application-supplied `Executor` bean | Boot may create an `AsyncTaskExecutor` of type `ThreadPoolTaskExecutor` |
| Auto-configured `ThreadPoolTaskExecutor` | **8 core threads**; tunable via `spring.task.execution.*` |
| Scheduler needed for `@Scheduled`, none provided by app | Boot may auto-configure `ThreadPoolTaskScheduler` |
| Boot's `ThreadPoolTaskScheduler` | **1 scheduler thread** by default; tunable via `spring.task.scheduling.*` |
| Java 21+ with `spring.threads.virtual.enabled=true` | Boot uses virtual-thread-friendly implementations such as `SimpleAsyncTaskExecutor` and `SimpleAsyncTaskScheduler`; pooling properties do not apply identically to virtual-thread schedulers |

Side-by-side with plain Spring Framework:

| Question | Spring Framework with annotations | Typical Spring Boot 3.3 auto-config |
| --- | --- | --- |
| Who chooses the executor? | Lookup unique `TaskExecutor` bean, then `Executor` named `taskExecutor`, then fallback | Boot may **supply the auto-configured bean**, which the Framework lookup then finds |
| No user executor present? | `SimpleAsyncTaskExecutor` fallback for `@Async` | Auto-configured `ThreadPoolTaskExecutor` if conditions match and virtual threads are off |
| "Default" core count? | No single number across all `TaskExecutor` types; directly constructed `ThreadPoolTaskExecutor` has core 1 | Boot-created pool has core 8 on platform threads |
| Default scheduler? | Internal single-threaded fallback scheduler if no bean found | Boot may create a `ThreadPoolTaskScheduler` bean, default pool size 1 |
| How to configure? | `@Bean`, setters, `AsyncConfigurer`, `SchedulingConfigurer`, qualifiers | Same Framework mechanisms, plus `spring.task.execution.*`/`spring.task.scheduling.*` for auto-config |

**Do not equate executor and scheduler:** `spring.task.execution.pool.core-size=8` does not give the scheduler eight threads. To get a 3-thread scheduler pool, use `spring.task.scheduling.pool.size=3` (with Boot's auto-configured scheduler) or the corresponding bean setter.

### 4.1. Commonly Used Properties

`src/main/resources/application.properties` in Boot 3.3 (effective only for matching auto-configuration):

~~~properties
# Boot-managed asynchronous tasks:
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=12
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=30s
spring.task.execution.thread-name-prefix=app-worker-

# Boot-managed scheduled tasks:
spring.task.scheduling.pool.size=2
spring.task.scheduling.thread-name-prefix=app-schedule-
~~~

These are **not default values**: they are **application-provided overrides**. Some values work meaningfully only together: `max-size` engages when a finite queue fills; once both queue and pool are full, tasks may be rejected per the rejection policy.

Boot configuration properties follow precedence rules: command-line args or environment variables can override config files per Boot's property source order. In real apps, never read `application.properties` alone to assume running values; inspect the resolved `Environment`, live beans, and active profiles.

### 4.2. When Defining Your Own Bean, Do Properties Apply Automatically?

Suppose the application declares:

~~~java
// Snippet inside @Configuration; not a complete class.
@Bean("applicationTaskExecutor")
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    return executor;
}
~~~

For this bean, the 2/4/16 setters are **application configuration**. Never expect that adding `spring.task.execution.pool.core-size=8` will cause Boot to overwrite values set manually: Boot auto-config typically **backs off** once a custom `Executor` bean exists, and a bean built with manual setters does not automatically bind the entire `spring.task.execution.*` namespace.

If you want Boot configuration properties applied to a custom bean, use Boot's appropriate builder (such as `ThreadPoolTaskExecutorBuilder`, pre-configured by Boot from the environment) or bind properties explicitly; verify the builder and API for your exact Boot version. Avoid configuring through multiple channels without knowing which source wins.

### 4.3. Two Easily Confused Names: `taskExecutor` and `applicationTaskExecutor`

In Spring Framework, `taskExecutor` is the prominent fallback name for `@EnableAsync` when no unique `TaskExecutor` exists. In Spring Boot 3.3, the auto-configured executor is normally named **`applicationTaskExecutor`**; integrations such as Spring MVC asynchronous request processing look for a matching `AsyncTaskExecutor` under that name.

If an application defines multiple `Executor` beans, `@Async`'s default choice and MVC's executor choice can diverge. A bean named `reportExecutor` neither automatically becomes the default for all async paths nor guarantees MVC uses it.

How to eliminate ambiguity:

1. For important background jobs, use `@Async("reportExecutor")` or inject `@Qualifier("reportExecutor") TaskExecutor`.
2. For Spring MVC async, verify the `AsyncTaskExecutor` named `applicationTaskExecutor` or configure `AsyncSupportConfigurer` for MVC.
3. For `@Scheduled`, explicitly target `taskScheduler` or configure `SchedulingConfigurer`; it requires a **scheduler**, not an arbitrary executor.
4. When multiple contexts exist, each context has its own beans and annotation rules; do not rely on beans from another context.

## 5. Runnable Example: Comparing Boot Defaults and Custom Beans

This example uses **Java 17, Maven, and Spring Boot 3.3.13**, without a web server. It prints **the actual bean implementation and values** across two runs: (a) Boot auto-configuration, and (b) application-declared custom pools. Virtual threads are disabled in this example.

Structure:

~~~text
pool-defaults/
├── pom.xml
└── src/main/java/com/example/pools/
    ├── PoolDefaultsApplication.java
    ├── AuditService.java
    └── CustomPools.java
~~~

### 5.1. pom.xml

~~~xml
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
    <artifactId>pool-defaults</artifactId>
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

### 5.2. PoolDefaultsApplication.java

~~~java
package com.example.pools;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class PoolDefaultsApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolDefaultsApplication.class, args);
    }

    @Bean
    ApplicationRunner auditPools(
            ApplicationContext context, AuditService auditService) {
        return args -> {
            ThreadPoolTaskExecutor executor = context.getBean(
                    "applicationTaskExecutor", ThreadPoolTaskExecutor.class);
            ThreadPoolTaskScheduler scheduler = context.getBean(
                    "taskScheduler", ThreadPoolTaskScheduler.class);

            System.out.println("EXECUTOR_TYPE="
                    + executor.getClass().getSimpleName());
            System.out.println("CORE=" + executor.getCorePoolSize());
            System.out.println("MAX=" + executor.getMaxPoolSize());
            System.out.println("QUEUE_CAPACITY=" + executor.getQueueCapacity());
            System.out.println("SCHEDULER_TYPE="
                    + scheduler.getClass().getSimpleName());
            System.out.println("SCHEDULER_CORE="
                    + scheduler.getScheduledThreadPoolExecutor().getCorePoolSize());

            // Runs @Async via bean proxy; thread name may vary.
            String worker = auditService.workerName().get(5, TimeUnit.SECONDS);
            System.out.println("WORKER_THREAD=" + worker);
        };
    }
}
~~~

`getCorePoolSize()`, `getMaxPoolSize()`, and `getQueueCapacity()` report pool configuration. They **do not** report active worker count: to inspect live state use `getActiveCount()`, `getPoolSize()`, `getQueueSize()`, or metrics. For the scheduler, read `getScheduledThreadPoolExecutor().getCorePoolSize()` to observe the configured core size on `ScheduledThreadPoolExecutor`. At startup there are usually not enough tasks to create all workers; never confuse "current pool size" with "configured core size."

### 5.3. AuditService.java

~~~java
package com.example.pools;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AuditService {
    @Async("applicationTaskExecutor")
    public CompletableFuture<String> workerName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

`workerName()` is invoked from another bean via the proxy and explicitly targets `applicationTaskExecutor`. Returning `CompletableFuture` lets the demo wait for the result to print; in real background endpoints, avoid calling `get()` on the request thread when fast responses are desired.

### 5.4. CustomPools.java

~~~java
package com.example.pools;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "demo.custom", havingValue = "true")
public class CustomPools {
    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor appExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(12);
        executor.setThreadNamePrefix("custom-worker-");
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler scheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(3);
        scheduler.setThreadNamePrefix("custom-schedule-");
        return scheduler;
    }
}
~~~

When `demo.custom=true` is absent, neither `@Bean` above is **declared** due to the class-level condition. Spring Boot can auto-create the corresponding executor and scheduler. When the flag is enabled, the application-declared beans appear; Boot's matching auto-config backs off, and the application's setters determine the values. Every number (2, 4, 12, 3) in `CustomPools` is **custom** configuration, not a Framework default.

To ensure Boot recognizes that a scheduler is needed, the demo enables `@EnableScheduling`. If your project has no scheduling needs, omit it and the scheduler part; auto-configuration depends on the Boot version's registration conditions.

### 5.5. Running Both Modes

Run from the directory containing `pom.xml` (requires JDK 17+ and Maven):

~~~bash
# Mode A: use Boot auto-configuration when no custom bean exists.
mvn spring-boot:run

# Stop the app before continuing, e.g., Ctrl+C.
# Mode B: enable the two application-declared beans.
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.custom=true"
~~~

**Mode A** (Spring Boot 3.3.13 on Java 17, no other `Executor`; ignoring framework log lines and varying worker name suffixes):

~~~text
EXECUTOR_TYPE=ThreadPoolTaskExecutor
CORE=8
MAX=2147483647
QUEUE_CAPACITY=2147483647
SCHEDULER_TYPE=ThreadPoolTaskScheduler
SCHEDULER_CORE=1
WORKER_THREAD=task-1
~~~

The line `WORKER_THREAD=task-1` is an **example thread name**, not a guaranteed string under different configuration, shared usage by other components, or a custom thread factory. The numbers printed from getters are the primary comparison points in this controlled environment.

**Mode B** (custom beans from `CustomPools`; likewise ignoring logs):

~~~text
EXECUTOR_TYPE=ThreadPoolTaskExecutor
CORE=2
MAX=4
QUEUE_CAPACITY=12
SCHEDULER_TYPE=ThreadPoolTaskScheduler
SCHEDULER_CORE=3
WORKER_THREAD=custom-worker-1
~~~

The final thread name value is also illustrative; the `custom-worker-` prefix is set by the application. **Both modes use `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler`, yet with different configurations.** Therefore you cannot look solely at the class name in logs and assume "defaults" are in effect.

**Demo limitations:** no `spring.task.execution.pool.*` properties are set, so Mode A shows Boot's baseline; adding properties or environment variables changes the numbers. There is no `@Scheduled` task in the example; the scheduler bean is still created by Boot because scheduling is enabled, though real scheduled execution requires an `@Scheduled` method.

### 5.6. If You Only Want to Change Boot Properties Without Adding Beans

You can stay in Mode A and pass arguments:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--spring.task.execution.pool.core-size=3 --spring.task.execution.pool.max-size=5 --spring.task.execution.pool.queue-capacity=10 --spring.task.scheduling.pool.size=2"
~~~

When Boot creates both pools, getters are expected to reflect `CORE=3`, `MAX=5`, `QUEUE_CAPACITY=10`, and `SCHEDULER_CORE=2`. Command-line argument parsing here is forwarded by the Spring Boot Maven plugin; in PowerShell, keep the double quotes around the entire `-Dspring-boot.run.arguments=...` value.

Conversely, passing `demo.custom=true` alongside those properties leaves `CustomPools` applying 2/4/12 and 3 via setters, because it does not use Boot's builder to read those properties. This is a **reproducible experiment** separating Boot-provided config from application-declared config.

## 6. Why Might max-size Fail to Take Effect?

Even when configured numbers are known, `ThreadPoolTaskExecutor` behavior depends on the underlying `ThreadPoolExecutor` algorithm.

With core=2, max=4, queueCapacity=12:

1. While two workers are busy, new tasks can enter the queue.
2. When the queue reaches its limit and the pool is below max, the executor can open extra workers.
3. Once the pool hits max and the queue is full, new tasks may be rejected (`TaskRejectedException` via Spring `TaskExecutor`); design backpressure and return HTTP 429/503 when appropriate.
4. Queued tasks add latency; inflating the queue too much can mask overload and force requests to wait too long before running.

With an unbounded queue like `ThreadPoolTaskExecutor`'s initial default, the pool mostly stays at core even when max is set very high. Thus a claim like "max=100 runs 100 jobs in parallel" is usually false without checking the queue. Conversely, a large pool does not guarantee throughput if the real bottleneck lies in a connection pool, database, or external API.

In real applications, match pools to workload traits: CPU-bound work should not multiply workers endlessly; I/O-bound work may need higher concurrency while respecting resource limits and timeouts. Separate pools for slow/long jobs and fast SLA-sensitive jobs so one cannot starve the other's queue.

## 7. Java 21 and Virtual Threads Change How "Default" Is Interpreted

Spring Boot 3.3 supports enabling virtual threads on Java 21+ via `spring.threads.virtual.enabled=true`. Boot may then auto-configure:

- `SimpleAsyncTaskExecutor` using virtual threads instead of standard `ThreadPoolTaskExecutor`;
- `SimpleAsyncTaskScheduler` instead of a traditional platform-thread scheduler pool.

Consequently, `spring.task.execution.pool.core-size` or `spring.task.scheduling.pool.size` **cannot be interpreted as a maximum number of virtual threads**. With `SimpleAsyncTaskScheduler`, fixed-delay tasks follow special rules involving a scheduler thread; check the documentation for that implementation.

Virtual threads do not exempt you from DB connection limits, sockets, API quotas, or CPU limits; use semaphores/rate limits and monitor under load. Simply running on Java 21 with virtual threads does not automatically turn a custom `ThreadPoolTaskExecutor` into a virtual-thread executor: conditions and bean types still matter.

## 8. How to Determine the Actual Configuration in a Running System

Follow this checklist sequence:

1. **Pin down versions:** running Spring Framework, Spring Boot, and Java versions; are virtual threads enabled?
2. **Check enabled features:** are `@EnableAsync`, `@EnableScheduling`, and annotated methods active in the context?
3. **List beans:** inspect `Executor`, `TaskExecutor`, `AsyncTaskExecutor`, `TaskScheduler`, and `ScheduledExecutorService` beans; check names, types, and counts.
4. **Verify selection rules:** does `@Async("name")` have a qualifier? Is there an `AsyncConfigurer`? Where does `SchedulingConfigurer` point the registrar? Are there name collisions on `taskExecutor`/`applicationTaskExecutor`/`taskScheduler`?
5. **Inspect config sources:** resolved `Environment`, active profiles, command-line args, YAML/properties; see whether Boot auto-config or app code created the bean.
6. **Read runtime state:** getters for core/max/queue/pool size, active thread count, current pool size, queue length, and rejection metrics; export via Micrometer/Actuator if instrumented.
7. **Load and shutdown test:** measure wait times, task rejections, context propagation, timeouts, and whether shutdown waits for running jobs.

Java snippet to list executors and schedulers from `ApplicationContext` (place in an allowed runner/debug utility; this is a snippet, not a standalone program):

~~~java
String[] executors = context.getBeanNamesForType(
        java.util.concurrent.Executor.class);
String[] schedulers = context.getBeanNamesForType(
        org.springframework.scheduling.TaskScheduler.class);

System.out.println("Executor beans = " + java.util.Arrays.toString(executors));
System.out.println("Scheduler beans = " + java.util.Arrays.toString(schedulers));
~~~

Bean names and counts depend on the full application context. This verifies existence, which is **not enough** to conclude which bean an annotation picks; cross-check lookup rules and qualifiers. Retrieving a bean solely by broad type when multiple beans exist can throw `NoUniqueBeanDefinitionException`; use name + type or `@Qualifier` to be certain.

### Template for Recording Config Decisions During Code Review

| Review item | Details to record |
| --- | --- |
| Framework / Boot / JDK | Exact deployed versions |
| Workloads | Which `@Async`, `@Scheduled`, MVC async, or explicit `execute` calls |
| Selected executor | Actual bean name and class, bean creation source |
| Thread pool | core, max, queue, keepAlive, rejection policy |
| Scheduler | bean name/type, thread count, cron/fixedDelay/fixedRate, and timezone |
| Override source | code setters, Boot properties, env vars, profiles, builders |
| Operations | active/queued/rejected, SLA, shutdown, retries, idempotency |

Using this table in reviews explains why two environments that are "both Spring Boot" can exhibit different thread counts and performance.

## 9. Common Mistakes

| Misconception / symptom | Root cause | Fix |
| --- | --- | --- |
| "Spring Framework defaults to 8 workers." | Core 8 is the baseline of **Boot 3.3's auto-configured platform-thread executor**, not every `TaskExecutor` | Identify who creates the bean and its runtime type |
| "`new ThreadPoolTaskExecutor()` defaults match Boot." | Direct class default core=1; Boot builder may set core=8 | Print getters, set properties explicitly |
| "Set `max-size=20`, must run 20 tasks." | An unbounded queue can keep the pool at core | Design finite queues and test saturation |
| "Edited `application.properties` but pool didn't change." | Custom bean doesn't use Boot binding/builder, or another source overrides it | Check bean source and resolved environment |
| "`@Async` isn't running in the background." | Async not enabled, self-invocation, or `SyncTaskExecutor` selected | Check `@EnableAsync`, proxy, and thread name |
| "`@Scheduled` runs in parallel after raising execution core." | Executor pool and scheduler pool are separate | Configure `spring.task.scheduling.pool.size` or a custom scheduler |
| "Named it `reportExecutor`, so MVC uses it too." | MVC has specific expectations around `AsyncTaskExecutor`/`applicationTaskExecutor` | Configure MVC async explicitly |
| "All `@Async` methods use the bean I just declared." | Multiple beans, qualifiers, or `AsyncConfigurer` control selection | Specify `@Async("beanName")` and audit |
| "One scheduler covers the whole cluster." | Each application context/pod runs its own scheduler | Use distributed locks, idempotency, or a dedicated scheduler |
| "Virtual threads still have pool-size 8." | Auto-config may select a different implementation | Check actual class and cap external resources |

Some failures appear only under multi-instance deployments or heavy load. Clean startup and one passing request **do not prove** optimal pool selection.

## 10. Self-Check Exercises

1. In plain Spring Framework with `@EnableAsync`, there is no unique `TaskExecutor` and no `Executor` bean named `taskExecutor`. Which fallback does Spring use? Does it reuse pooled workers?
2. Do `new ThreadPoolTaskExecutor()` and a Spring Boot 3.3 auto-configured `ThreadPoolTaskExecutor` share the same default core size? Why or why not?
3. Boot auto-configures an executor with core=8, and you add `@Bean("applicationTaskExecutor")` with core=2. Which source determines the actual core size?
4. An application has two `TaskExecutor` beans: `imageExecutor` and `reportExecutor`. Which does an unqualified `@Async` pick? What must change for deterministic behavior?
5. Why might increasing `spring.task.execution.pool.max-size` while leaving an unbounded queue fail to increase concurrency?
6. Which pool does `@Scheduled` use, and why doesn't changing the async executor configuration necessarily make cron jobs run concurrently?
7. After enabling Java 21 virtual threads, why must you check the executor/scheduler class before interpreting `core-size` and `pool.size`?
8. If two pods run the same cron job at midnight, will raising pool size or renaming beans prevent duplicate data updates? What coordination mechanism is needed?

**Practical conclusion:** whenever someone mentions "Spring defaults," always ask for the **version, class, bean creator, executor selection rule, and effective configuration source**. Only after answering those can you accurately state how many threads a pool uses or which property an application should tune.

## References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — @EnableScheduling Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)