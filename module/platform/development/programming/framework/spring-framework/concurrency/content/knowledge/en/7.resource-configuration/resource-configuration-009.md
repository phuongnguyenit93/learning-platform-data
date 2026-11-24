# Distinguishing Spring Framework Configuration from Spring Boot Auto-Configuration

## 1. Purpose and Scope

In Spring, you can write `@Configuration` and `@Bean` to create a `ThreadPoolTaskExecutor` or `ThreadPoolTaskScheduler`. When using Spring Boot, an application sometimes already has similar beans even when you wrote no Java configuration at all. These two phenomena often lead learners to wrong conclusions—that "Spring Framework creates thread pools by itself," that "adding `@Async` means Boot automatically enabled async," or that "changing `spring.task.execution.pool.*` always updates every executor."

This lesson distinguishes **two layers of responsibility**:

1. **Spring Framework** provides the IoC container, bean configuration, `TaskExecutor`/`TaskScheduler` abstractions, implementations, `@Async` processing proxies, and `@Scheduled` registration mechanics. You can declare them in a plain Spring app without Spring Boot.
2. **Spring Boot** sits on top of Spring Framework, providing dependency management, application bootstrap, **conditional auto-configuration**, externalized configuration via properties/YAML, and convenient defaults. When conditions match, Boot creates executor/scheduler beans for you; when user-defined beans exist, results may differ.

The content focuses on **execution resource configuration** in concurrency: executors, schedulers, bean selection, thread pools, property effectiveness, lifecycle, and verification. You need to know how to trace: **which beans exist, who created them, who uses them, which configuration is in effect, and who shuts down the resources**.

Java code examples use Java 17+ with Spring Framework 6.1 / Spring Boot 3.3 as a verifiable baseline; the virtual threads section requires Java 21+. The principles apply broadly, while exact defaults and auto-configuration conditions must be checked against your actual version.

## 2. Understanding the Layers Properly

```text
                 BUSINESS CODE
     @Async service, @Scheduled task, caller
                        |
            Select executor/scheduler
                        |
        +---------------+---------------+
        |                               |
  Spring Framework                Spring Boot
  - @Configuration                - @SpringBootApplication
  - @Bean                         - @EnableAutoConfiguration
  - @EnableAsync                  - AutoConfiguration conditions
  - @EnableScheduling             - @ConfigurationProperties
  - TaskExecutor API              - spring.task.execution.*
  - TaskScheduler API             - spring.task.scheduling.*
  - ThreadPoolTaskExecutor        - Default bean if conditions match
  - ThreadPoolTaskScheduler
        |                               |
        +---------------+---------------+
                        |
                 Java / JVM / OS
          ThreadPoolExecutor / virtual threads
```

**Key point:** Boot **uses** Framework components and adds auto-configuration logic. Boot does not change the nature of `ThreadPoolTaskExecutor` or the Java Memory Model. Framework does not need Boot to run tasks; Boot cannot make shared mutable state automatically thread-safe.

### 2.1. Comparison Table

| Aspect | Plain Spring Framework | Spring Boot |
| --- | --- | --- |
| Goal | DI infrastructure, bean lifecycle, AOP, task execution/scheduling SPI | Fast bootstrap, component setup driven by classpath and config |
| Where resources are declared | Typically `@Configuration`/`@Bean`, XML, bean definitions | Manual beans **or** auto-configured beans |
| Enabling async annotations | `@EnableAsync` or matching XML config | Still needs `@EnableAsync` when using that annotation mechanism |
| Enabling scheduling | `@EnableScheduling` or matching XML | Still needs scheduling enablement, usually `@EnableScheduling` |
| Selecting executor | `@Async("beanName")`, `AsyncConfigurer`, default lookup | Same Framework rules, plus auto-configured executor and Boot integrations |
| Tuning pool | Call setters during bean creation or bind app properties manually | Provides `spring.task.execution.*` for matching auto-configured executors |
| Tuning scheduler | Create scheduler bean or via `SchedulingConfigurer` | Provides `spring.task.scheduling.*` when auto-configured scheduler applies |
| Auto-creation conditions | No default Boot auto-config mechanism | Classpath + existing bean conditions + settings + version |
| Lifecycle | Container-created beans are managed by container; manual outside container must be closed manually | Container still manages beans; Boot helps wire/configure auto-configured beans |
| Verification | Read config, list beans, observe threads/executors | Same, plus condition evaluation report and Actuator if present |

Crucially, distinguish four **separate** actions: (1) creating an executor bean, (2) enabling annotation processing, (3) selecting the actual executor for a call, and (4) configuring that executor's resources. Doing one does not automatically prove the other three.

## 3. Plain Spring Framework: You Declare Beans Intentionally

In a Spring Framework-only application, `@Configuration` and `@Bean` are the direct way to declare resources. The Framework handles dependency injection, bean initialization/destruction, and proxies for enabled annotations. It does not automatically read Spring Boot's `spring.task.execution.pool.*` namespace.

### 3.1. Creating a Pool and Binding It Explicitly to `@Async`

Complete runnable example using **Java 17 + Maven** and **Spring Framework 6.1.x**, without Spring Boot.

Structure:

```text
framework-only/
├── pom.xml
└── src/main/java/demo/FrameworkOnlyDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>framework-only</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>
</project>
```

File `src/main/java/demo/FrameworkOnlyDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class FrameworkOnlyDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("manualExecutor")
        ThreadPoolTaskExecutor manualExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setThreadNamePrefix("manual-");
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            return executor;
        }

        @Bean
        Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("manualExecutor")
        public CompletableFuture<Boolean> checkExecutor() {
            boolean selected =
                    Thread.currentThread().getName().startsWith("manual-");
            return CompletableFuture.completedFuture(selected);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Worker worker = context.getBean(Worker.class);
            boolean selected = worker.checkExecutor()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("manual-executor=" + selected);
        }
    }
}
```

Run in the directory containing the POM:

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.FrameworkOnlyDemo
```

Program output line (Maven may print its own messages depending on environment):

```text
manual-executor=true
```

**Why this works:** `@EnableAsync` registers `@Async` processing infrastructure; calling the method on a Spring-managed bean lets the proxy intercept it; `@Async("manualExecutor")` explicitly names the executor bean; the task verifies the prefix on the executing thread. `try-with-resources` closes the application context, through which Spring runs `ThreadPoolTaskExecutor` bean lifecycle shutdown.

Notice there is no `SpringApplication.run`, `@SpringBootApplication`, or `spring.task.execution.*` property here—because this is **plain Spring Framework**. You change executor names and parameters entirely through bean configuration.

### 3.2. What If the Framework Has No Executor You Created?

When `@EnableAsync` is used without configuring an executor, the Framework's async mechanism looks for a matching `TaskExecutor` (or `Executor` with conventional name `taskExecutor`) and has fallbacks like `SimpleAsyncTaskExecutor`. That fallback is **not a Boot-configured bounded pool**, and does not mean a load-appropriate resource was provisioned.

Hence, "the code runs" only confirms the call executed; it does not prove worker counts, queues, load limits, or shutdown are suitable. For production apps, specify executors explicitly and test overload behavior.

### 3.3. Do Not Forget the Scheduler

Framework provides `TaskScheduler`, `ThreadPoolTaskScheduler`, and `@EnableScheduling`. You can declare one manually:

```java
@Configuration
@EnableScheduling
class FrameworkSchedulingConfig {
    @Bean("maintenanceScheduler")
    ThreadPoolTaskScheduler maintenanceScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("manual-schedule-");
        return scheduler;
    }
}
```

This is a **fragment** inside a Spring project with matching imports, not a standalone Java file. Do not confuse `@EnableScheduling` (activating annotation processing) with the scheduler bean (providing the resource). If multiple schedulers exist, check how Spring picks a default or configure explicitly via `SchedulingConfigurer`; giving a bean an arbitrary name does not prove every `@Scheduled` method uses it.

## 4. Spring Boot: Beans Created by Conditional Auto-Configuration

`@SpringBootApplication` includes Boot's auto-configuration mechanism (via `@EnableAutoConfiguration`) along with configuration/scanning. Boot inspects the classpath, existing beans, and configuration property values, then evaluates conditions such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty`.

**Conditional auto-configuration** means Boot usually creates resources **when corresponding beans are missing and conditions are met**. It does not guarantee the exact same bean types in every Boot application. Adding a custom executor bean can cause auto-configuration for the default executor to **back off** (skip creating that bean). Exact conditions vary by Boot version and bean type.

In **Spring Boot 3.3.x**, when no custom `Executor` is present:

- Boot can auto-configure an `AsyncTaskExecutor`. When virtual threads are disabled, the default implementation is `ThreadPoolTaskExecutor`.
- With Java 21+ and `spring.threads.virtual.enabled=true`, the auto-configured executor can be `SimpleAsyncTaskExecutor` using virtual threads.
- Spring async integration, Spring MVC async requests, and other components follow distinct rules for using auto-configured beans; both bean name and bean type matter.
- When scheduled execution with `@EnableScheduling` is needed, Boot can auto-configure a scheduler; with platform threads it is typically `ThreadPoolTaskScheduler`, while with virtual threads it can be `SimpleAsyncTaskScheduler`.
- Boot provides `spring.task.execution.*` and `spring.task.scheduling.*` properties to tune **Boot-auto-configured resources**, subject to matching conditions.

These details come from official Spring Boot 3.3.x documentation; for Boot 4.x or other releases, consult the matching version reference.

### 4.1. Boot Example: Configuring Solely via `application.yml`

Assume a **Spring Boot 3.3.x** project with `spring-boot-starter`, Java 17+, no custom `Executor` or `AsyncConfigurer` bean declared, and virtual threads disabled.

File `src/main/resources/application.yml`:

```yaml
spring:
  main:
    web-application-type: none
  threads:
    virtual:
      enabled: false
  task:
    execution:
      thread-name-prefix: boot-work-
      pool:
        core-size: 2
        max-size: 4
        queue-capacity: 20
        keep-alive: 30s
    scheduling:
      thread-name-prefix: boot-schedule-
      pool:
        size: 2
```

The project needs no `@Configuration` class manually creating `ThreadPoolTaskExecutor` for Boot to configure the executor from these properties. Yet **for `@Async` annotations to be processed**, `@EnableAsync` is still required; and for `@Scheduled`, `@EnableScheduling` is normally required.

File `src/main/java/demo/BootAutoExecutorDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class BootAutoExecutorDemo {
    @Bean
    Worker worker() {
        return new Worker();
    }

    public static class Worker {
        @Async("applicationTaskExecutor")
        public CompletableFuture<Boolean> checkExecutor() {
            boolean selected =
                    Thread.currentThread().getName().startsWith("boot-work-");
            return CompletableFuture.completedFuture(selected);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(BootAutoExecutorDemo.class, args)) {
            AsyncTaskExecutor executor =
                    context.getBean("applicationTaskExecutor",
                                    AsyncTaskExecutor.class);
            boolean selected = context.getBean(Worker.class)
                    .checkExecutor().get(5, TimeUnit.SECONDS);

            System.out.println("bean-type=" +
                    executor.getClass().getSimpleName());
            System.out.println("boot-executor=" + selected);
        }
    }
}
```

Run in a Boot project configured with Gradle wrapper and matching Java:

```bash
./gradlew bootRun
```

Two expected application lines on **Boot 3.3.x under the exact conditions above**, aside from startup logs:

```text
bean-type=ThreadPoolTaskExecutor
boot-executor=true
```

Boot creates the `applicationTaskExecutor` bean when conditions match; `@Async("applicationTaskExecutor")` selects it explicitly; the `boot-work-` prefix comes from `application.yml`. Looking up the bean by both name and type prevents thinking "a task ran, so it must have used the right pool."

Enabling virtual threads, adding a manual executor bean, changing Boot version, or missing an appropriate starter can change bean types and output. The example states explicit conditions to avoid treating one scenario as an immutable default.

### 4.2. Adding Properties Alone Does Not Enable Annotation Processing

Three configurations serve distinct roles:

| What You Add | What It Does | What It Does Not Do Automatically |
| --- | --- | --- |
| `@EnableAsync` | Enables Spring proxy interception for `@Async` | Does not automatically provision a load-ready bounded pool |
| `spring.task.execution.pool.max-size=...` | Tunes a property of the Boot-managed pool when applicable | Does not register `@Async` or modify custom beans that do not bind the property |
| `@Async("someExecutor")` | Designates an executor for a method when advice actually runs | Does not create a bean named `someExecutor` |
| `@EnableScheduling` | Enables `@Scheduled` annotation processing | Does not turn cron into a durable job |
| `spring.task.scheduling.pool.size=...` | Tunes Boot-managed scheduler thread pool when effective | Does not necessarily affect code-created schedulers |
| `@Bean ThreadPoolTaskExecutor` | Registers a custom resource in the container | Does not mean Boot applies every `spring.task.execution.*` to that bean |

Internal `this.doAsync()` calls within the same bean normally bypass the default `@Async` proxy. Even when Boot properly created `applicationTaskExecutor`, self-invocation can still run the method on the caller thread. That is a Framework proxy mechanic, **not a Boot auto-configuration bug**.

## 5. What Happens When You Declare Your Own Executor in Spring Boot?

Spring Boot respects application customization. Once an `Executor` is declared, auto-configuration may stop creating the default executor; meanwhile, integrations still have their own bean-name and type expectations. This is the single most common cause of "I edited YAML, yet the thread count didn't change."

### 5.1. Custom Bean Pattern

In a Spring Boot app, the following configuration creates a `ThreadPoolTaskExecutor` whose parameters **you** own:

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class CustomExecutionConfig {
    @Bean("domainExecutor")
    ThreadPoolTaskExecutor domainExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("domain-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

This is a **Spring fragment** placed in a project with dependencies. If a method carries `@Async("domainExecutor")` and is invoked through the Spring proxy, it uses this bean. Changing `spring.task.execution.pool.core-size` in YAML **does not automatically replace** the `3` set by the setter in the code above.

You can move parameters into your own `@ConfigurationProperties`, or use a Boot-provided builder (e.g., `ThreadPoolTaskExecutorBuilder` in corresponding versions) to leverage customizers/settings, while verifying which properties actually bound. Creating a bean with `new` does not mean Boot automatically binds properties onto it.

### 5.2. Distinguishing `taskExecutor` and `applicationTaskExecutor` Beans

This is an easy source of confusion between **general async methods** and **integrations**:

- Framework `@Async` processing: looks for a default executor via `AsyncConfigurer`, a matching `TaskExecutor` bean, or the conventional name `taskExecutor`; `@Async("beanName")` specifies one explicitly per method.
- Per **Spring Boot 3.3** documentation, when multiple `Executor` beans exist, normal async support can fall back by the name `taskExecutor`.
- For Spring MVC async requests and Spring WebFlux blocking execution support on Boot 3.3, the integration expects a matching `AsyncTaskExecutor` named `applicationTaskExecutor`.
- `ThreadPoolTaskExecutor` is an `AsyncTaskExecutor`, whereas a plain `java.util.concurrent.ExecutorService` does not automatically satisfy every Spring MVC async integration requirement.
- Two different beans can coexist for different purposes; a bean "working for `@Async`" does not prove it also handles MVC `Callable`/`WebAsyncTask`.

Scenario matrix on Boot 3.3.x:

| Context | What to Verify |
| --- | --- |
| No custom `Executor`, using Boot auto-config | `applicationTaskExecutor` exists with right bean type and prefix/size |
| One custom `Executor` bean declared | Did Boot back off? Which bean does `@Async` pick? Does MVC still have a valid executor? |
| Multiple `Executor` beans | How do `AsyncConfigurer`, a `taskExecutor` bean, and `@Async("...")` resolve selection? |
| Want MVC async to use a custom bean | Is there an `AsyncTaskExecutor` named `applicationTaskExecutor`, or explicit MVC config? |
| Want a dedicated pool for domain work | Use `@Async("domainExecutor")` and inject via `@Qualifier` |
| Virtual threads enabled | What type is the auto-configured bean? Do pool-size properties still apply? |

**Do not** rename a bean arbitrarily just to make the app boot. Bean names are part of the wiring contract across integrations; renaming can silently shift a component onto a different pool.

### 5.3. Keeping Boot's Default for MVC While Using a Dedicated Domain Pool

An intentional design often looks like:

- Let Spring MVC async use the `applicationTaskExecutor` bean of type `AsyncTaskExecutor`.
- Let heavy business methods use `@Async("domainExecutor")`.
- Document explicitly which bean serves which role, using `AsyncConfigurer` if setting a default for `@Async`.
- Check auto-configuration conditions for your exact Boot version: adding `domainExecutor` may cause Boot **to stop creating** `applicationTaskExecutor` automatically. In that case, declare a dedicated MVC bean or use a Boot-supported configuration pattern.
- Set queues, rejections, timeouts, metrics, and shutdown individually per workload type.

Never assume "Boot will always fill in whichever pool is missing" once custom executors exist. Inspect the actual bean list from the application context after startup.

## 6. Practical Example: Fixing an Ineffective Configuration Bug

Suppose a Boot app contains:

```yaml
spring:
  task:
    execution:
      pool:
        core-size: 8
        max-size: 16
        queue-capacity: 100
```

Yet the source code also has:

```java
@Bean("fileExecutor")
ThreadPoolTaskExecutor fileExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(1000);
    return executor;
}
```

And a file-processing method:

```java
@Async("fileExecutor")
public CompletableFuture<String> processFile(String name) {
    return CompletableFuture.completedFuture(name);
}
```

These fragments require matching imports/project setup. If the call passes through the proxy, the executor used is `fileExecutor` with core/max **2** and queue **1000** per the Java config; editing YAML for the Boot-managed executor does not alter setters already called on the `fileExecutor` bean.

**Fix procedure:**

1. Confirm which bean `@Async("fileExecutor")` points to; verify calls go through the proxy.
2. Decide on one configuration source: Java setters, custom `@ConfigurationProperties` bound to the bean, or a verified Boot builder/integration.
3. Change values in the source actually used by `fileExecutor`, rather than editing an unreferenced property.
4. Verify `getCorePoolSize()`, `getMaxPoolSize()`, queue capacity, and thread prefix on the **bean actually executing tasks**.
5. Load test to confirm queue → worker scaling → rejection behavior; do not just compare config text.

If adding an `Executor` causes Boot auto-config to back off and another integration loses `applicationTaskExecutor`, resolve that integration's wiring too. That is an architectural impact to catch, not just a pool-size issue.

## 7. How Do Auto-Configuration Conditions Work?

An auto-configuration expresses a conditional decision, **conceptually** like:

```text
If relevant classes/features exist on classpath
  and execution mode matches
  and no user bean matches exclusion conditions
then create default executor/scheduler
otherwise skip default creation.
```

This is a mental model, **not the exact condition code** of a specific Boot release. Annotations like `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty` are used by auto-configuration; exact condition classes, bean names, and bean types must be checked in your current release.

### 7.1. Order and Timing of Condition Evaluation

- Auto-configuration is imported into the application context by Boot, not invoked manually by you as a function.
- Conditions evaluate against bean definitions, classpath, environment, and configuration available at the appropriate phase.
- If a custom bean triggers an exclusion condition, auto-config skips Boot's default; that is by design so the application retains control.
- If source code has `@Bean` in a class outside component-scan/import scope, the bean may **not exist** in the context you are inspecting.
- If a method has `@Async` without async processing enabled, or is called on a `new`-instantiated object, the annotation will not produce an async call.
- A Framework `@Configuration` class works inside Boot too, since Boot uses the same container; the difference is simply that Boot adds auto-configurations.

### 7.2. How to Inspect Why a Bean Was or Was Not Created

In Boot, you can:

1. Start with condition evaluation debugging enabled (e.g., `--debug` where supported) and read the condition evaluation report.
2. With Actuator, inspect conditions and beans endpoints when enabled/authorized, such as `/actuator/conditions` and `/actuator/beans`. Avoid exposing sensitive endpoints publicly.
3. Inspect the actual beans in `ApplicationContext` and their runtime classes.
4. Check `@ConditionalOnMissingBean`, `@ConditionalOnClass`, and property binding in the docs/source of your exact Boot release.
5. Check active profiles and external override order. `application.yml` is not necessarily the final word if environment variables or CLI args override it.
6. Cross-check observed thread names, pool metrics, and context wiring. A thread-name prefix alone does not prove every task shares one executor, yet combined with bean IDs and futures it makes diagnosis clear.

With plain Framework (no Boot), inspect bean definitions, `getBeansOfType`, and Java/XML config; there is **no** Boot condition report without Boot.

## 8. Verifying at Runtime with Code, Not Guesswork

### 8.1. Listing Executor and Scheduler Beans

The following fragment can live inside a component of a Boot or Spring Framework project; it assumes `ApplicationContext context` is injected and `Map`, `Executor`, `TaskScheduler`, `ThreadPoolTaskExecutor` are imported.

```java
Map<String, Executor> executors =
        context.getBeansOfType(Executor.class);

executors.forEach((name, executor) -> {
    String type = executor.getClass().getName();
    System.out.println("Executor " + name + " -> " + type);

    if (executor instanceof ThreadPoolTaskExecutor pool) {
        System.out.println("core=" + pool.getCorePoolSize());
        System.out.println("max=" + pool.getMaxPoolSize());
        System.out.println("poolSize=" + pool.getPoolSize());
        System.out.println("active=" + pool.getActiveCount());
    }
});

Map<String, TaskScheduler> schedulers =
        context.getBeansOfType(TaskScheduler.class);

schedulers.forEach((name, scheduler) ->
        System.out.println("Scheduler " + name + " -> " +
                           scheduler.getClass().getName()));
```

This is an **integration fragment**, not a standalone Java class. It reveals **which beans exist and their config** in the context. However, a bean existing does not prove methods actually use it; still trace `@Async` qualifiers, `AsyncConfigurer`, injections, and MVC/WebFlux integrations.

Do not read `getPoolSize()` and mistake it for `maxPoolSize`: pool size is the current number of existing workers at observation time; max is the configured upper bound. And once tasks finish, `activeCount` can read 0 even though the executor previously ran work.

### 8.2. Checking Whether an `@Async` Method Actually Switches Threads

Service fragment:

```java
@Async("domainExecutor")
public CompletableFuture<Boolean> onDomainPool() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName().startsWith("domain-"));
}
```

A caller in **another bean** invokes the service via the Spring proxy and checks `future.get(timeout)`. Do not call `this.onDomainPool()` from inside the service to test it. You can also record trace IDs, executor names, and durations in test environments to cross-check.

For `void` methods, there is no future to carry errors back to the caller; use `AsyncUncaughtExceptionHandler`/logging/monitoring appropriately. For `CompletableFuture`, exceptions surface when the future completes exceptionally and the caller observes it.

### 8.3. Verifying Scheduling

In Spring, the presence of a `ThreadPoolTaskScheduler` does not prove all `@Scheduled` methods are active. Check:

- Are `@EnableScheduling` and Spring management of the bean in place?
- Is an appropriate scheduler present and selected?
- Are cron time zones, fixed rate/delay, concurrency, and task overlap properly understood?
- Are multiple application instances running the same schedule simultaneously?
- Do business results require exactly-once/durability guarantees beyond a local scheduler?

Short scheduled callbacks can run directly on the scheduler; long-running callbacks usually need task offloading. With multiple replicas, `@Scheduled` alone never guarantees cluster-wide single execution.

## 9. Executors and Schedulers: Two Separate Auto-Config Tracks

An application may need `@Async` without `@Scheduled`, or vice versa. Distinguish them:

| Need | Framework Abstraction | Conditional Boot Support | Reference Property Namespace |
| --- | --- | --- | --- |
| Submit async tasks | `TaskExecutor` / `AsyncTaskExecutor` | Auto-configured executor if conditions match | `spring.task.execution.*` |
| Bound async worker pool | `ThreadPoolTaskExecutor` | Tunes pool if bean is a thread pool managed by Boot | `spring.task.execution.pool.*` |
| Schedule tasks | `TaskScheduler` | Auto-configured scheduler when needed and conditions match | `spring.task.scheduling.*` |
| Bound scheduler workers | `ThreadPoolTaskScheduler` | Pool properties if matching pool implementation is used | `spring.task.scheduling.pool.*` |
| Run tasks with virtual threads | `SimpleAsyncTaskExecutor`/virtual-thread executor per version | Boot 3.3 supports enabling via property | `spring.threads.virtual.enabled` |

A Boot 3.3.x example can use:

```yaml
spring:
  task:
    execution:
      thread-name-prefix: background-
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 64
    scheduling:
      thread-name-prefix: clock-
      pool:
        size: 2
```

If you only declare `@EnableScheduling`, Boot can auto-create a scheduler under matching conditions; if your app declares a custom `ThreadPoolTaskScheduler`, do not assume `spring.task.scheduling.pool.size` applies to that bean. If using Boot's virtual-thread scheduler, `pool-size` may not apply. Always trace the actual object in use.

### 9.1. Default Schedulers Are Not Durable Job Queues

Boot makes creating a scheduler convenient, yet creating a scheduler bean does not solve:

- jobs surviving a JVM crash/restart;
- distributed locking across multiple instances;
- retries and idempotency;
- persistent success/failure state tracking;
- guaranteeing a job completes once across the whole cluster.

Those belong to business job management or external orchestration. Never mistake auto-configuration for a durability promise.

## 10. Virtual Threads and Differences Across Boot Versions

On Java 21+, virtual threads can be used for many **blocking I/O** workloads; they do not give databases/downstream APIs infinite connections or make CPU-bound work faster than core count.

In Spring Boot 3.3.x when supported, `spring.threads.virtual.enabled=true` changes the implementation of auto-configured executors/schedulers. Boot may use:

- `SimpleAsyncTaskExecutor` with virtual threads instead of the auto-configured `ThreadPoolTaskExecutor`;
- `SimpleAsyncTaskScheduler` with virtual threads instead of `ThreadPoolTaskScheduler` where scheduling applies.

In that mode, **platform-thread pool** properties like core/max/queue/pool.size may no longer govern the new mechanism. This applies only to the auto-configured path; it does not automatically turn custom `@Bean ThreadPoolTaskExecutor` definitions into virtual-thread executors.

Boot 3.3.x example on Java 21+:

```yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
```

Virtual threads are daemon threads; for background/scheduled apps with no other non-daemon threads keeping the JVM alive, appropriate keep-alive settings prevent unexpected process exit. Verify your exact Boot version and runtime.

**Never treat virtual threads as "flip a flag and all problems vanish."** You must still measure active tasks, CPU, memory, connection pools, timeouts, and backpressure. With virtual-thread schedulers, certain fixed-delay modes have scheduler-thread characteristics to watch; do not assume `pool-size` scales parallelism like a legacy thread pool.

## 11. Who Creates and Who Shuts Down Resources?

Not only which beans exist, but **lifecycle ownership** differs too.

### 11.1. Spring-Managed Resources

When `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` is a bean with a Spring-recognized lifecycle, the context runs appropriate initialization and destruction callbacks. Both manual beans in Framework and Boot-auto-configured beans can be managed by the Spring container.

`ThreadPoolTaskExecutor` shutdown settings to consider:

- `setWaitForTasksToCompleteOnShutdown(...)`: policy for waiting/continuing accepted tasks when the context closes, depending on Spring version behavior.
- `setAwaitTerminationSeconds(...)`: time bound the context waits for the executor to terminate per supported mechanism; not a guarantee every task finishes.
- Retries/cancellation/timeouts and external graceful shutdown if tasks can be interrupted or container-killed.

If business tasks must survive restarts, an in-memory executor is insufficient: use durable jobs/queues/workflows and design duplicate/idempotency handling.

### 11.2. Resources Not Managed by the Container

Example:

```java
public void process() {
    ExecutorService executor = Executors.newFixedThreadPool(4);
    executor.submit(() -> runWork());
}
```

This is a **broken lifecycle fragment** if `executor` is never retained/closed. Spring/Boot does not discover and shut down arbitrary executors instantiated in local methods. Either create a reusable managed bean or ensure the owning code closes it with `shutdown()`, awaits completion/cancels as required, and handles errors.

### 11.3. Lifecycle Ownership by Bean Source

| Resource Source | Who Chooses Configuration? | Who Normally Manages Lifecycle? |
| --- | --- | --- |
| `@Bean ThreadPoolTaskExecutor` in plain Spring | Application code | Spring container if managed bean |
| Auto-configured executor in Boot | Boot + properties + conditions | Spring container |
| Custom `@Bean` in Boot | Application code / intentional binding | Spring container |
| Local `Executors.new...` | Method/class creating the executor | The owner itself must close it |
| Jakarta EE managed executor | Application server container | External container; app must not shut down arbitrarily |
| Broker/job worker | Infrastructure + worker manager | Follows the job system's own lifecycle |

Thus "manual Spring Framework" and "Boot auto" differ mainly in **where the bean definition and config policy come from**, while runtime lifecycle can still flow through the same Spring container.

## 12. Environment-Specific Configuration: Local, Test, Staging, Production

In plain Spring Framework, you create conditional beans via `@Profile`, `@Conditional`, or custom externalized config binding. In Boot, auto-configuration and property sources cut boilerplate, yet make it easy to assume a number written in one YAML file is always the final value.

Boot config sources can include `application.yml`, profile-specific files, environment variables, system properties, command-line arguments, and config imports. Precedence follows Boot's externalized configuration rules. Always verify the effective environment and runtime bean.

Hypothetical example:

- `application.yml`: `spring.task.execution.pool.core-size=4`;
- production profile: changes it to 8;
- custom `@Bean`: calls `setCorePoolSize(2)` without binding properties;
- actual task: `@Async("domainExecutor")` runs on the custom bean.

Here someone reading YAML might think production runs eight workers, yet **domainExecutor** still has core 2 unless other logic overrides it. Always inspect the bean running the task and its binding path, not just config files.

### 12.1. A Single Auditable Configuration Source

If you choose a custom bean for specific business requirements, do the following:

- Define a dedicated namespace, e.g., `app.executors.domain.core-size` / `queue-capacity`, bound explicitly via `@ConfigurationProperties`.
- Use those bound values when constructing `ThreadPoolTaskExecutor`.
- Validate legal bounds—e.g., core does not exceed max, queue is non-negative unless special semantics are handled.
- Emit metrics and test property binding under the production profile.
- Never use two ambiguous sources simultaneously without knowing which takes precedence.

If you stick with pure auto-configuration, avoid creating unnecessary `Executor` beans that alter conditions. Helper components can simply inject `AsyncTaskExecutor` without declaring a new executor.

## 13. Relationship to Spring MVC, WebFlux, and Transaction Context

Spring MVC handles requests on servlet container threads, whereas `@Async` tasks usually run on application executors; MVC async controller return types have their own executor integration path. In Boot 3.3, `applicationTaskExecutor` matters for several web integrations. If you name a bean `domainExecutor` for `@Async`, **do not assume** Spring MVC async requests also use that same bean.

Spring WebFlux favors non-blocking pipelines; never configure a custom pool and then call blocking APIs directly on the event loop. Framework blocking-offload support follows its own integration rules; consult guides for your version and stack.

For transactions, Spring `@Transactional` normally binds to the executing thread via proxy/context mechanisms. Crossing into `@Async` does not carry the caller's transaction onto the worker automatically. Security context, MDC, and request-scoped state also require deliberate propagation. These challenges exist identically in plain Spring Framework and Boot, because Boot does not erase thread boundaries.

A `TaskDecorator` can copy permitted context items, provided it cleans up properly and is tested with worker thread reuse. Never pass whole request objects or `EntityManager` across workers just to preserve context.

## 14. Failure Causes and Troubleshooting

| Symptom | Common Causes | Verification Step |
| --- | --- | --- |
| `@Async` runs on request thread | Missing `@EnableAsync`, self-invocation, non-bean object | Print caller/worker threads, inspect proxy and config |
| Two pools exist, task hits "wrong pool" | Multiple `Executor`s, mismatched names/qualifiers/defaults | Inspect `@Async("...")`, `AsyncConfigurer`, `taskExecutor` bean |
| Changing `spring.task.execution.pool.*` has no effect | Custom executor declared or virtual-thread strategy active | Print actual class/core/max and read condition report |
| Missing `applicationTaskExecutor` bean | Auto-config backed off due to custom bean/conditions | List beans and inspect Boot conditions |
| MVC async ignores custom `Executor` | Wrong type (not `AsyncTaskExecutor`) or wrong bean name | Check integration requirements and MVC config |
| `@Scheduled` never runs | Scheduling not enabled or method not on Spring-managed bean | Check `@EnableScheduling` and context |
| Schedule runs multiple times across cluster | Each instance runs its own scheduler | Add coordination/locking and job idempotency |
| Many tasks remain on shutdown | Long queue, slow tasks, missing cancellation/timeouts | Monitor queue, graceful shutdown, and deadlines |
| Boot uses virtual threads and `pool-size` has no effect | Implementation is not a platform-thread pool | Inspect runtime class and virtual-thread property |
| Named executor bean lacks metrics | Missing instrumentation or wrong bean inspected | Check object identity/name and instrument the right pool |
| Missing-bean error when migrating Framework to Boot | Assuming starters enable every annotation automatically | Verify `@EnableAsync`/`@EnableScheduling` and conditions |
| Tests pass but production fails | Tests use `SyncTaskExecutor`, runtime uses async pool | Test with real executors and synchronize with latches |

### 14.1. Investigation Order When "Properties Have No Effect"

1. Confirm exact Java, Spring Framework, and Spring Boot versions.
2. Identify where work runs: `@Async` method, MVC async controller, scheduler callback, or direct `executor.execute()`.
3. Identify the actual bean selected by qualifier/configurer/integration.
4. Print bean name, runtime type, core/max/queue, thread prefix; check metrics.
5. Check whether that bean came from an app `@Bean` or Boot auto-configuration.
6. Inspect effective environment, profiles, properties, and config binding.
7. Read the condition evaluation report to see why Boot did or did not create default beans.
8. Fix the authoritative config source, then re-verify with thread names and load tests.

Never raise max threads without understanding queue policy. With `ThreadPoolExecutor`, the pool usually fills core workers first, then places tasks into the queue; only when the queue cannot accept more does it scale workers toward max. An unbounded queue can keep max from ever taking effect as expected.

## 15. Learning Through Two Contrasting Scenarios

### Scenario A: Plain Spring Framework Processing 200 File Imports

You declare `@Bean("importExecutor")` returning a `ThreadPoolTaskExecutor`, setting core/max/queue and rejection policy. You enable `@EnableAsync`, place `@Async("importExecutor")` on a Spring-managed bean method, and call it from another bean.

Verification: `@Configuration` code is the source of bean definitions; thread prefixes prove tasks use the right pool; closing the context verifies lifecycle. To vary settings per profile, you intentionally build config-binding logic (or conditional beans).

### Scenario B: Spring Boot 3.3.x MVC App Needing Light Background Work

Without needing a custom executor, you can let Boot auto-configure `applicationTaskExecutor` and tune it via `spring.task.execution.*`. Still enable `@EnableAsync` for method annotations. If you later add a custom `Executor` for imports, re-check auto-configuration and MVC async integration.

Verification: Boot's condition report identifies the auto-configured bean, `ApplicationContext` confirms name/type, thread prefixes and metrics confirm execution; properties count as effective only when bound to the actual bean in use.

### Same Business Code, Two Configuration Paths

```java
@Service
public class ImportService {
    @Async("importExecutor")
    public CompletableFuture<Integer> importFiles(List<String> paths) {
        return CompletableFuture.completedFuture(paths.size());
    }
}
```

This is a **fragment requiring imports and a Spring project**; you must provide an `importExecutor` bean in both environments if using this qualifier. Using Spring Boot **does not imply** a bean named `importExecutor` is auto-configured: Boot creates default beans under different names. To use `@Async` without a qualifier, verify which default executor resolves in each environment.

## 16. Hands-On Exercise Testing the Differences

Build **two small applications** sharing the same `WorkerService` with `@Async`, computing a simple result:

**Part 1 — Plain Framework:**
1. Create `AnnotationConfigApplicationContext`, `@Configuration`, and `@EnableAsync`.
2. Define `@Bean("manualExecutor") ThreadPoolTaskExecutor` with prefix `manual-`, core 2, max 4, queue 10.
3. Use `@Async("manualExecutor")`, invoked from another Spring-managed bean.
4. Print thread names and await `CompletableFuture.get(timeout)`; verify the prefix.
5. Close the context and verify no new tasks are accepted once the executor shuts down.

**Part 2 — Boot:**
1. Create a Boot 3.3.x project with `@SpringBootApplication` and `@EnableAsync`.
2. Add no custom `Executor`; set `spring.task.execution.thread-name-prefix=boot-` and pool properties.
3. Inspect the `applicationTaskExecutor` bean and its runtime class/config.
4. Add `@Bean("customExecutor")` with prefix `custom-`; restart.
5. Record which beans still exist, why auto-config may have backed off, and which bean `@Async` uses.
6. Apply `@Async("customExecutor")` and verify tasks route to the right pool.
7. If using Spring MVC async, separately verify the `applicationTaskExecutor` bean and `AsyncTaskExecutor` type.

**Part 3 — Scheduling and Environments:**
1. Add `@EnableScheduling` and a `@Scheduled(fixedDelay = 5000)` method.
2. With no custom scheduler, observe Boot's scheduler bean when conditions match.
3. Add a custom `ThreadPoolTaskScheduler` and check which bean `spring.task.scheduling.pool.size` affects.
4. Run on Java 21+ with virtual threads enabled (if supported by your release) and compare executor/scheduler types and what `pool-size` means.
5. Run two simulated replicas and confirm each process runs its own scheduler; propose coordination if only one cluster-wide job should run.

**Part 4 — Testing and Observation:**
1. Use a bounded queue and submit more tasks than capacity to observe rejection. Avoid `sleep` to guess ordering; use latches to hold workers.
2. Measure core/max, active count, queue depth, and latency.
3. Close the context while tasks remain; inspect shutdown policy and timeouts.
4. Trace `"config source → bean → caller/annotation → thread → lifecycle"` for each case.

### Self-Assessment Checklist

- [ ] I can distinguish Framework `@Configuration`/`@Bean` from Boot's conditional auto-configuration.
- [ ] I know `@EnableAsync`/`@EnableScheduling` and creating executor/scheduler resources are two separate steps.
- [ ] I can predict **when** Boot skips creating default beans due to a custom `Executor`.
- [ ] I understand the differences among bean names/types `taskExecutor`, `applicationTaskExecutor`, and `@Async` qualifiers.
- [ ] I do not assume `spring.task.execution.pool.*` tunes every custom executor.
- [ ] I know why Spring MVC async and `@Async` methods may use different executors.
- [ ] I know how virtual threads change the meaning of pool properties on matching auto-configured paths.
- [ ] I can identify who owns an executor and who shuts it down on application exit.
- [ ] I can prove behavior via runtime bean inspection, condition reports, and real task execution tests.
- [ ] I verify all these rules against the **actual Spring Boot release in use**, rather than copying defaults from another version.

**Key takeaway:** Spring Framework supplies the **mechanisms and abstractions** to configure execution resources; Spring Boot supplies **conditional beans and defaults** to reduce manual boilerplate. To understand how a concurrent app actually runs, trace **annotation → executor/scheduler bean → bean origin → properties/binding → actual threads and lifecycle**.

## 17. Official Versioned Reference Documentation

- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `TaskScheduler`, `@EnableAsync`, `@EnableScheduling`, implementation choices, and qualification.
- Spring Boot 3.3 — [Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): auto-configured executor/scheduler conditions, `applicationTaskExecutor` bean name, pool properties, and virtual threads.
- Spring Boot — [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, profiles, and override rules.
- Spring Boot — [SpringApplication and Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html): JDK requirements, `spring.threads.virtual.enabled` property, and keep-alive.

Current documentation can change across Spring Framework/Boot upgrades. For a concrete project, **check docs matching your exact dependency versions and inspect runtime beans/condition reports** before applying defaults to production.
