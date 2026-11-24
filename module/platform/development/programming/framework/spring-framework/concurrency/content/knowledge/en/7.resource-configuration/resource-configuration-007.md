# Configuring TaskExecutor and TaskScheduler via @Bean or the XML task Namespace

## 1. Purpose of Configuring Concurrency Resources

Spring Framework provides abstractions for **executing tasks** (`TaskExecutor`) and **scheduling tasks** (`TaskScheduler`). An application must create and configure an appropriate implementation, register it in the Spring `ApplicationContext`, and inject it into the components that need it.

There are two common ways to declare them in Spring Framework:

1. **Java configuration**: write a `@Bean` method inside a `@Configuration` class, instantiate the executor/scheduler, and configure it via setters.
2. **XML configuration**: use elements from the **task namespace**, such as `<task:executor>`, `<task:scheduler>`, and `<task:annotation-driven>`. XML also supports standard declarations via `<bean class="...">` and `<property>`.

Both approaches share the same goal: register beans in the container so business code depends on interfaces rather than managing thread pool lifecycles itself. Switching between Java and XML does not make an application faster by itself; the choice depends on module conventions, operational requirements, project structure, and maintainability.

```text
             Configuration, one choice per application/context
                  /                             \
       Java @Configuration                 Spring XML
       @Bean executor()                    <task:executor .../>
       @Bean scheduler()                   <task:scheduler .../>
                  \                             /
                   \                           /
               ApplicationContext / bean registry
                       |              |
                     TaskExecutor   TaskScheduler
                       |              |
                 submit Runnable   schedule a task
                       |              |
                     workers / clock / concurrency controls
```

Key design point: the **bean definition** determines how resources are created and managed; **client code** only needs to know the contract it uses.

## 2. Distinguishing TaskExecutor and TaskScheduler Before Configuring

| Characteristic | `TaskExecutor` | `TaskScheduler` |
| --- | --- | --- |
| Purpose | Accepts tasks for execution per executor policy | Runs tasks at a specified time or on a schedule |
| Representative API | `execute(Runnable)` | `schedule(...)`, fixed-rate/fixed-delay variants |
| Common implementation | `ThreadPoolTaskExecutor` | `ThreadPoolTaskScheduler` |
| Java configuration | `ThreadPoolTaskExecutor` bean | `ThreadPoolTaskScheduler` bean |
| Shorthand XML configuration | `<task:executor .../>` | `<task:scheduler .../>` |
| Related annotation | `@Async` | `@Scheduled` |

**Do not confuse them:** declaring an executor bean alone does not automatically activate `@Async`; declaring a scheduler alone does not automatically activate `@Scheduled` in plain Spring Framework. To process annotations, Java configuration needs `@EnableAsync` / `@EnableScheduling` respectively, or XML needs `<task:annotation-driven .../>`.

Both resource types can coexist and serve distinct kinds of work. A scheduler deciding *when* a task runs is not the same as a general executor deciding *how* tasks are accepted and dispatched to workers.

## 3. Configuring ThreadPoolTaskExecutor via @Bean

Example bean method inside a Java configuration class:

```java
@Configuration(proxyBeanMethods = false)
public class TaskInfrastructureConfig {

    @Bean("workExecutor")
    public ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("work-");
        return executor;
    }
}
```

This is a **fragment**; it requires importing `org.springframework.context.annotation.Configuration`, `org.springframework.context.annotation.Bean`, and `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`. A full runnable version appears in Section 7.

Analysis:

- `@Configuration` marks the class as containing bean definitions. `proxyBeanMethods=false` is appropriate when `@Bean` methods do not call each other directly to obtain container-managed beans.
- `@Bean("workExecutor")` assigns a stable identifier to the executor. You can inject by name when the application has multiple executors.
- `corePoolSize=2`: the pool creates up to 2 core workers as tasks arrive (not necessarily pre-started by default).
- `maxPoolSize=4`: maximum worker limit when the queue cannot accept tasks.
- `queueCapacity=8`: selects a `LinkedBlockingQueue` holding at most 8 waiting tasks. With `queueCapacity=0`, Spring uses a `SynchronousQueue` for handoff with no backlog storage.
- `threadNamePrefix="work-"`: helps identify threads in logs, thread dumps, and profilers.

With a positive queue, `ThreadPoolExecutor`'s standard admission rule is **create core threads → enqueue → grow up to max if queue is full → reject if both pool and queue are full**. Thus raising `maxPoolSize` alone while keeping a huge queue may prevent the pool from scaling as expected.

The numbers 2/4/8 here are purely illustrative. In production, choose values based on load, CPU, task duration, DB/HTTP limits, timeouts, and latency requirements.

### Lifecycle of an Executor Bean

When `ThreadPoolTaskExecutor` is a Spring-managed bean, the container applies the required lifecycle callbacks to initialize the executor and coordinate shutdown. Do not manually call `afterPropertiesSet()` inside the `@Bean` method only for Spring to initialize it again.

In a standalone program where you manually instantiate `new ThreadPoolTaskExecutor()` **without** a container, you must initialize and shut down the pool properly yourself. Bean configuration keeps this responsibility in one place. For critical background tasks, still check shutdown/await-termination settings; never assume every task always completes on exit.

## 4. Configuring ThreadPoolTaskScheduler via @Bean

To schedule work, you can use:

```java
@Bean("workScheduler")
public ThreadPoolTaskScheduler workScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-");
    return scheduler;
}
```

This is also a fragment, placed in a `@Configuration` class and requiring `ThreadPoolTaskScheduler` imported. It has a pool to handle scheduled triggers, **not the `queueCapacity` of a regular executor**.

If you want Spring to detect `@Scheduled` methods:

```java
@Configuration
@EnableScheduling
public class SchedulingConfig {
    // TaskScheduler beans and beans with @Scheduled methods.
}
```

A Spring-managed bean method can declare:

```java
@Scheduled(fixedDelay = 5_000)
public void refreshCache() {
    // Cache refresh logic.
}
```

These fragments require `org.springframework.scheduling.annotation.EnableScheduling` and `Scheduled`. They are **semantic illustrations**, not a standalone runnable program. `fixedDelay` measures delay after the **previous execution completes**; `fixedRate` expresses a period measured from start time per the scheduler's mechanism. With multiple threads, long tasks, retries, and shared resources, analyze overlap potential, delays, and idempotency; do not treat scheduling as an exactly-once execution guarantee in distributed systems.

## 5. The XML task Namespace in Spring

Namespace syntax lets you describe resource configuration without listing full class names for every bean.

### 5.1. Declaring the Namespace and Schema

Header of a valid XML context:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:task="http://www.springframework.org/schema/task"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/task
           https://www.springframework.org/schema/task/spring-task.xsd">

    <!-- Bean definitions go here. -->
</beans>
```

The `task` namespace is simply a prefix mapped to Spring's schema URI; the string `task` itself is not a bean name. Missing `xmlns:task` or the URI/schemaLocation pair can cause XML parser schema or unbound-prefix errors.

### 5.2. Creating an Executor with `<task:executor>`

```xml
<task:executor id="workExecutor"
               pool-size="2-4"
               queue-capacity="8"
               rejection-policy="ABORT"
               keep-alive="60"/>
```

Here:

- `id="workExecutor"` is the Spring bean name; that same name can be referenced from `@Qualifier`, `@Async("workExecutor")`, or XML attributes.
- `pool-size="2-4"` sets core size to 2 and max size to 4. A single value like `pool-size="4"` sets both core and max to 4 (a fixed worker-limit pool).
- `queue-capacity="8"` creates a queue holding up to 8 items; `queue-capacity="0"` chooses a handoff queue with no backlog.
- `rejection-policy="ABORT"`: when the executor is overloaded, tasks are rejected via abort policy; Spring may raise `TaskRejectedException`.
- `keep-alive="60"`: idle time (seconds) before non-core workers can be reclaimed.

This XML declaration matches the core parameters of the `@Bean("workExecutor")` method in Section 3. The Java version adds a custom `threadNamePrefix`; in namespace form, Spring uses `id` as the basis for thread name prefixes. Do not assume thread names will be identical across the two configuration styles.

Another example illustrating caller backpressure:

```xml
<task:executor id="limitedExecutor"
               pool-size="3-6"
               queue-capacity="20"
               rejection-policy="CALLER_RUNS"/>
```

When the pool and queue are overloaded, `CALLER_RUNS` can cause the calling thread to run the task itself (if the executor is still active). This policy slows down the caller, yet can cause severe latency if the caller is an HTTP request worker or event-loop thread. It is not suitable by default for every system. Task-dropping policies like `DISCARD` must be evaluated carefully to avoid losing business work.

### 5.3. Creating a Scheduler with `<task:scheduler>`

```xml
<task:scheduler id="workScheduler" pool-size="2"/>
```

This element creates a `ThreadPoolTaskScheduler` with pool size 2. If `pool-size` is omitted, Spring uses one thread per default namespace configuration. Do not apply `<task:executor>`'s `queue-capacity` to `<task:scheduler>`; they are two different bean types.

### 5.4. Enabling `@Async` and `@Scheduled` via XML

```xml
<task:annotation-driven
    executor="workExecutor"
    scheduler="workScheduler"/>
```

Here `executor` references the bean used to process `@Async` methods and `scheduler` references the bean managing `@Scheduled`. This declaration differs from merely creating executor/scheduler beans: it **enables the corresponding annotation processing**.

The equivalent in Java configuration is `@EnableAsync` and/or `@EnableScheduling` on appropriate `@Configuration` classes. If work is only submitted via `TaskExecutor.execute(...)`, enabling annotation processing is not required.

Note: In standard Spring proxy mode, calling an `@Async` method from another method on the **same object** (`this.asyncMethod()`) bypasses the proxy, so it does not dispatch to the executor as an external call through the Spring-managed proxy would.

### 5.5. Scheduling Entirely in XML

Without `@Scheduled` annotations, the namespace can also register periodic calls on a bean:

```xml
<task:scheduler id="reportScheduler" pool-size="2"/>

<task:scheduled-tasks scheduler="reportScheduler">
    <task:scheduled ref="reportService"
                    method="generate"
                    fixed-delay="5000"
                    initial-delay="1000"/>
</task:scheduled-tasks>
```

This is an **XML fragment** requiring `reportService` to be a bean with a compatible `generate()` method. `fixed-delay="5000"` corresponds to 5,000 ms after the previous run finishes, `initial-delay="1000"` is 1,000 ms before the first run; schedules can also be declared with `fixed-rate` or `cron` as needed.

Do not register the *same task* twice via both `@Scheduled` and `<task:scheduled-tasks>` unintentionally; duplicate triggers can cause repeated execution.

## 6. How Does the XML task Namespace Differ from Plain XML `<bean>`?

Besides shorthand syntax, you can declare the concrete class explicitly:

```xml
<bean id="workExecutor"
      class="org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor">
    <property name="corePoolSize" value="2"/>
    <property name="maxPoolSize" value="4"/>
    <property name="queueCapacity" value="8"/>
    <property name="threadNamePrefix" value="work-"/>
</bean>
```

This is an XML alternative **replacing** `<task:executor id="workExecutor".../>`; do not declare two beans with the same id side by side in the same context.

| Criterion | Java `@Bean` | XML `<task:executor>` | XML `<bean>` |
| --- | --- | --- | --- |
| Configuration language | Java with compile-time type checking | Shorthand schema-based XML | XML listing class/properties |
| Conditional/logic flexibility | `@Profile`, conditional configs, Java code | Depends on XML/profile structure | Depends on XML/profile structure |
| Customizing specific properties | Direct setter API access | Limited to attributes exposed by the namespace | Access to implementation bean properties |
| Implementation name | Explicit in Java code | Hidden behind namespace syntax | Explicit in `class` attribute |
| Bean lifecycle | Managed by Spring container | Managed by Spring container | Managed by Spring container |

When you need specialized properties like `taskDecorator` that `<task:executor>` does not expose directly, use a `@Bean` method or XML `<bean>` with officially supported properties.

Do not assume XML is "dead legacy": Spring Framework still supports XML bean definitions and the `task` namespace; however, in new applications, Java configuration is generally easier for IDEs to check and refactor.

## 7. Runnable Experiment: Java Config and XML with the Same Service

The goal is to **swap the bean registration style while keeping business code identical**. The example uses Java 21, Maven, and Spring Framework 6.2.1; no Spring Boot required. The program includes both a method submitting directly to the executor and a method using `@Async`.

### 7.1. Structure

```text
spring-task-config-demo/
├── pom.xml
└── src/main/
    ├── java/demo/TaskConfigDemo.java
    └── resources/task-context.xml
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-task-config-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <configuration>
          <mainClass>demo.TaskConfigDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**File `src/main/java/demo/TaskConfigDemo.java`:**

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class TaskConfigDemo {

    public static class WorkService {
        private final TaskExecutor executor;

        public WorkService(TaskExecutor executor) {
            this.executor = executor;
        }

        public CompletableFuture<String> submit(String job) {
            CompletableFuture<String> result = new CompletableFuture<>();
            executor.execute(() -> result.complete("processed:" + job));
            return result;
        }

        @Async("workExecutor")
        public CompletableFuture<String> asyncHandle(String job) {
            return CompletableFuture.completedFuture("async:" + job);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class JavaConfig {
        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("work-");
            return executor;
        }

        @Bean("workScheduler")
        public ThreadPoolTaskScheduler workScheduler() {
            ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(2);
            scheduler.setThreadNamePrefix("schedule-");
            return scheduler;
        }

        @Bean("workService")
        public WorkService workService(
                @Qualifier("workExecutor") TaskExecutor executor) {
            return new WorkService(executor);
        }
    }

    public static void main(String[] args) throws Exception {
        boolean xml = args.length > 0 && "xml".equals(args[0]);
        String mode = xml ? "xml" : "java";

        try (ConfigurableApplicationContext context = xml
                ? new ClassPathXmlApplicationContext("task-context.xml")
                : new AnnotationConfigApplicationContext(JavaConfig.class)) {
            WorkService service =
                    context.getBean("workService", WorkService.class);

            String result = service.submit("J1")
                    .get(5, TimeUnit.SECONDS);
            String asyncResult = service.asyncHandle("J2")
                    .get(5, TimeUnit.SECONDS);

            System.out.println("mode=" + mode);
            System.out.println("execute=" + result);
            System.out.println("annotation=" + asyncResult);
            System.out.println("executor=" + context.getBean("workExecutor")
                    .getClass().getSimpleName());
            System.out.println("scheduler=" + context.getBean("workScheduler")
                    .getClass().getSimpleName());
        }
    }
}
```

The service has two ways of using the executor: `submit()` calls `execute()` directly; `asyncHandle()` uses the annotation and is dispatched by the Spring proxy. `main` interacts with the same working interface regardless of whether the XML or Java context is chosen.

**File `src/main/resources/task-context.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:task="http://www.springframework.org/schema/task"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/task
           https://www.springframework.org/schema/task/spring-task.xsd">

    <task:executor id="workExecutor"
                   pool-size="2-4"
                   queue-capacity="8"
                   rejection-policy="ABORT"
                   keep-alive="60"/>
    <task:scheduler id="workScheduler" pool-size="2"/>
    <task:annotation-driven
            executor="workExecutor" scheduler="workScheduler"/>

    <bean id="workService" class="demo.TaskConfigDemo$WorkService">
        <constructor-arg ref="workExecutor"/>
    </bean>
</beans>
```

The `$` in `class="demo.TaskConfigDemo$WorkService"` is the JVM syntax for a **nested static class**; do not replace it with a dot in this XML class string. The `workService` bean is constructed via the constructor taking `TaskExecutor`, matching the Java configuration.

### 7.2. Running with Java Configuration

In the project root directory:

```bash
mvn -q -DskipTests compile exec:java
```

**Standard program output** (excluding Maven/JVM messages if the environment prints extra logs):

```text
mode=java
execute=processed:J1
annotation=async:J2
executor=ThreadPoolTaskExecutor
scheduler=ThreadPoolTaskScheduler
```

The program was verified with Maven and the compiler using `maven.compiler.release=21`.

### 7.3. Running with the XML task Namespace

Keep the service source code unchanged, just pass one argument:

```bash
mvn -q -Dexec.args=xml exec:java
```

**Standard program output:**

```text
mode=xml
execute=processed:J1
annotation=async:J2
executor=ThreadPoolTaskExecutor
scheduler=ThreadPoolTaskScheduler
```

The XML variant was also run and verified. Depending on Spring version and how infrastructure beans initialize, application logs **may show a `BeanPostProcessorChecker` warning** while registering `@Async`/`@Scheduled` processors; the verification run on Spring 6.2.1 showed that warning, yet the beans were still created and tasks completed. In operations, distinguish context-startup warnings from real configuration or runtime errors; never assume all warnings are harmless across every project.

To use the scheduler bean for `@Scheduled` in the **Java branch**, add `@EnableScheduling` to the configuration; in this example the Java branch enables only `@EnableAsync` because there is no `@Scheduled` method. The XML branch includes `<task:annotation-driven executor=... scheduler=.../>` to demonstrate both capabilities.

### 7.4. What the Example Proves

- Java `@Bean` and XML `task` namespace both register the executor/scheduler under consistent bean names.
- `WorkService` has no knowledge of which configuration language defined the beans.
- `@Async("workExecutor")` works once annotation processing is enabled and the method is invoked through the Spring-managed proxy.
- `CompletableFuture.get(timeout)` lets the program perform a bounded wait and inspect results before closing the `ApplicationContext`.
- Executor configuration only handles accepting and running tasks in the current process; it does not create a durable queue or guarantee task completion if the process dies.

## 8. Wiring Services via Interfaces and Bean Names

When multiple executors exist, Spring must know which service uses which pool. With Java configuration, you can declare:

```java
@Bean
public ExportService exportService(
        @Qualifier("workExecutor") TaskExecutor executor) {
    return new ExportService(executor);
}
```

This is a fragment; `ExportService` is any service whose constructor accepts a `TaskExecutor`. `@Qualifier("workExecutor")` selects the bean by role without coupling the dependency type to `ThreadPoolTaskExecutor`.

The XML equivalent passes the dependency via constructor:

```xml
<bean id="exportService" class="demo.ExportService">
    <constructor-arg ref="workExecutor"/>
</bean>
```

Note that `demo.ExportService` must exist in your app if using this fragment; it only illustrates wiring. When only one matching `TaskExecutor` bean exists, Spring can autowire it; when multiple beans exist, explicit qualifiers/names prevent ambiguity or accidentally falling back to a default pool.

A well-written service simply calls `executor.execute(task)` to submit work; it does not need to know `pool-size`, `queue-capacity`, or XML schemas. Those settings belong to infrastructure.

## 9. @Async, @Scheduled, and Bean Definition vs. Annotation Enablement

There are three distinct steps:

1. **Register the implementation:** create a `ThreadPoolTaskExecutor` or `ThreadPoolTaskScheduler` bean.
2. **Register annotation processing:** use `@EnableAsync` / `@EnableScheduling` or `<task:annotation-driven>`.
3. **Bind methods to the mechanism:** place `@Async` / `@Scheduled` appropriately, or register `<task:scheduled-tasks>` when configuring schedules in XML.

Missing (1), tasks may use a default/fallback executor or lack desired limits. Missing (2), annotated methods may not be processed as expected. Missing (3), the executor bean may be created with nothing submitting work to it.

### 9.1. Choosing the Right Executor for @Async

In Java:

```java
@Async("workExecutor")
public CompletableFuture<String> generatePreview() {
    // Illustrative method on a Spring-managed bean.
    return CompletableFuture.completedFuture("done");
}
```

The method must be invoked by a client through the Spring proxy. Naming the executor in `@Async("workExecutor")` makes the target bean explicit. In XML, you can also set `executor="workExecutor"` on `<task:annotation-driven>` to pick a default executor for annotations that do not specify a name.

A common mistake is thinking `@Async` turns blocking JDBC/HTTP into non-blocking I/O: blocking calls still occupy an executor worker during the wait; it only moves the blocking point to another thread.

### 9.2. Choosing a Scheduler for @Scheduled

The scheduler governs trigger timing; it also has a pool size and lifecycle. If too many slow jobs run on a single-threaded scheduler, other scheduled runs can be delayed. Do not use a scheduler bean just to run a one-off `Runnable` like a general executor unless the design genuinely needs a scheduled trigger time.

Remember that in a multi-instance system, each instance has its own `ApplicationContext` and can run its own schedule. If business rules require only one instance to execute, use proper coordination or distributed locking; XML/annotations alone do not provide leader election.

## 10. Managing Configuration by Environment

### 10.1. Java @Profile

You can swap beans by profile:

```java
@Bean("workExecutor")
@Profile("dev")
public TaskExecutor developmentExecutor() {
    return new SyncTaskExecutor();
}

@Bean("workExecutor")
@Profile("!dev")
public ThreadPoolTaskExecutor productionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    return executor;
}
```

This is a fragment requiring imports for `@Profile`, `TaskExecutor`, `SyncTaskExecutor`, `ThreadPoolTaskExecutor` inside a configuration class. Both methods declare the same bean name, while only one profile branch should be active in a context under the condition. Note that `SyncTaskExecutor` runs work **immediately on the calling thread**, so timing behavior is completely different. Never assume synchronous tests reproduce production race conditions.

### 10.2. XML Profiles

XML supports `profile` attributes in bean definitions, provided schema rules, context scoping, and non-conflicting bean names across active profiles are respected. Example fragment describing environment-specific beans:

```xml
<beans profile="dev">
    <bean id="workExecutor"
          class="org.springframework.core.task.SyncTaskExecutor"/>
</beans>
<beans profile="prod">
    <task:executor id="workExecutor"
                   pool-size="4-8"
                   queue-capacity="100"/>
</beans>
```

This is a **fragment placed inside an appropriate root `<beans>`**, not a complete XML file. If using `<task:executor>` inside nested `<beans>`, verify that your schema and version permit that nesting. You can also split multiple XML config files and import the right file per environment. Always verify which beans actually exist in the context after activating profiles.

### 10.3. Distinguishing Spring Framework and Spring Boot

Spring Boot offers **auto-configuration** and properties such as `spring.task.execution.pool.core-size`, `spring.task.execution.pool.max-size`, and `spring.task.execution.pool.queue-capacity` depending on Boot version. These properties apply only when the corresponding auto-configured executor is in use; never assume a custom `@Bean("workExecutor")` automatically picks up Boot pool properties.

If your application uses plain Spring Framework, the `@Bean` methods and XML `task` namespace above work **without** Spring Boot or `application.properties`. Focus on the beans actually instantiated in the `ApplicationContext`.

## 11. Notes on Misconfiguration, Overload, and Operations

### 11.1. Bean Names and Ambiguity

Name beans after their function: `emailExecutor`, `reportExecutor`, `scheduledJobs`. Avoid generic names like `executor` when creating multiple beans of the same type without qualifying injection points. Duplicate bean names across Java configuration and XML loaded into the same context can cause conflicts, overrides, or rejections depending on settings; avoid declaring duplicate names when both configuration paths are loaded.

### 11.2. Overload, Queues, and Rejection

`ThreadPoolTaskExecutor` has its own pool and queue bounds. When both queue and workers are busy, tasks may be rejected by default (surfaced by Spring as `TaskRejectedException`). A normal return from `execute()` does not guarantee the task body succeeded; with async execution, worker-side exceptions have separate observation channels.

`rejection-policy="CALLER_RUNS"` is a throttling option, yet can block the calling thread for a long time; if the request server uses an event loop or limited workers, evaluate carefully before using it. Discard policies can drop work and are unsuitable for tasks that must complete.

### 11.3. Timeouts and Context Propagation

Tasks running on another thread may not inherit `ThreadLocal`, MDC, security context, or transaction context from the calling thread. Pass required inputs explicitly; use a `TaskDecorator` or proper propagation mechanism when observability metadata must carry over.

If tasks depend on databases/networks, configure client/dependency timeouts, inspect connection pools, and monitor queue wait; adding threads/queue does not substitute for fixing bottlenecks. When `@Async` methods return `Future`, capture exceptions or handle results properly. With `void` methods, errors do not automatically propagate back to the caller.

### 11.4. Shutdown and Runtime Environment

When the context closes, running threads and tasks follow each implementation's shutdown policy. Check await-termination settings, accept-after-close behavior, and plans to avoid losing critical tasks. Never use an in-memory executor as a durable queue for business work requiring replay after restart.

### 11.5. Practical Verification

After choosing a configuration style, verify:

- Beans exist with the expected names and types in `ApplicationContext`, without duplicate definitions across Java/XML branches.
- `corePoolSize`, `maxPoolSize`, `queueCapacity`, scheduler worker counts, and thread name prefixes match expectations.
- `@Async`/`@Scheduled` annotation processing is enabled and calls pass through the proxy.
- Under load, observe `activeCount`, `queueSize`, rejections, throughput, task execution time, p95/p99 wait times, and memory.
- Context shutdown does not abandon threads and queued work is not assumed durable.

## 12. Common Errors and Fixes

| Error | Consequence | How to Check/Fix |
| --- | --- | --- |
| Defining `@Bean executor` and expecting `@Async` to run | Annotation is not processed as expected | Enable `@EnableAsync` or `<task:annotation-driven>` and call via proxy |
| Defining a scheduler and expecting `@Scheduled` to run | Jobs are not registered from annotations | Enable `@EnableScheduling` or XML annotation-driven |
| Writing XML missing namespace/schema | Context fails to parse | Check `xmlns:task` and `schemaLocation` pairs |
| Writing `pool-size="2-4"` thinking 4 workers always run | Wrong concurrency estimate | Distinguish core/max; check queue-capacity |
| Huge queue while raising only `maxPoolSize` | Tasks wait long; pool rarely scales | Measure queue wait and tune core, max, and queue together |
| Importing both Java config and XML with colliding bean ids | Definition conflict/override | Pick one clear configuration source and inspect the bean registry |
| `@Async` self-invocation within the same bean | Bypasses default proxy | Call from another Spring-managed client bean |
| Using `TaskExecutor` for scheduling | Lacks scheduled trigger semantics | Use `TaskScheduler` and `@Scheduled`/scheduled-tasks |
| Instantiating executors with `new` in services without shutdown | Thread/resource leaks | Make the executor a Spring-managed bean |
| Treating submitted task as succeeded task | Missed worker exceptions | Use `Future`/`CompletionStage`; observe errors/rejections |
| Assuming XML namespace exposes every implementation feature | Missing specialized customizations | Use `@Bean` or `<bean>` for properties unsupported by the namespace |

## 13. Self-Check Questions

**Q1.** There is a `ThreadPoolTaskExecutor` bean named `workExecutor`, yet an `@Async("workExecutor")` method runs synchronously when called from the same bean. What should you check?

Check whether `@EnableAsync`/`<task:annotation-driven>` is present, and especially whether the call goes through `this.method()` and bypasses the Spring proxy. Also check the injected executor type and whether `SyncTaskExecutor` is in use.

**Q2.** Does XML `<task:executor pool-size="3-9" queue-capacity="100">` immediately spawn 9 threads at startup?

No. It configures core/max workers and queue capacity; core threads are typically created on demand as tasks arrive, and the pool only scales past core when the queue cannot accept more. Run load tests and observe actual behavior.

**Q3.** An application has both `@Bean("workExecutor")` and an imported XML declaring `<task:executor id="workExecutor">`. Should both be kept?

Avoid declaring two sources owning the same bean name in one `ApplicationContext`, unless an intentional override mechanism is designed. Choose one configuration source or organize profiles/files so each context has one active definition.

**Q4.** Can `ThreadPoolTaskExecutor` be swapped for `SyncTaskExecutor` in tests without editing the service?

Yes, if the service depends on the `TaskExecutor` interface. However, synchronous tests only verify submission logic and sequential execution; real concurrency issues still require dedicated tests.

**Q5.** Why does the XML example contain both `<task:scheduler>` and `<task:annotation-driven scheduler="...">`?

The first element **creates the scheduler resource**; the second **registers the mechanism that uses that scheduler to process annotations**. Keep bean creation and feature activation clearly separated.

## 14. Practical Summary

- **Java configuration:** use `@Bean` to create `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler`; enable `@EnableAsync` and/or `@EnableScheduling` when using annotations.
- **XML task namespace:** `<task:executor>` and `<task:scheduler>` define resources; `<task:annotation-driven>` activates `@Async`/`@Scheduled` processing; `<task:scheduled-tasks>` can declare schedules without annotations.
- **DI via interfaces:** business services depend on `TaskExecutor`/`TaskScheduler`, letting Java config or XML decide implementations, sizing, and lifecycle.
- **Do not skip operations:** thread pool size, queue capacity, rejection policies, shutdown, proxy behavior, and monitoring must all be verified on the actual beans.

### References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework 6.2 — @EnableAsync API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)