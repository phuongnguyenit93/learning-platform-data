# Injecting an Executor via Interface to Decouple From Implementation in Spring

## 1. The Problem: Business Logic Needs to Submit Tasks, Not Manage Thread Pools

Suppose an application needs to record business audit logs, send notifications, or generate reports after receiving a request. The business component needs to issue the command **"please execute this work"**. It does not necessarily need to know whether the work runs on a new thread, on a pool, on the current thread, or through an infrastructure-managed executor.

If a service creates `new Thread(...)` or `new ThreadPoolTaskExecutor()` itself, it starts taking on extra responsibilities: choosing thread counts, configuring queues, initializing, shutting down the executor, and managing resources. When you want to switch execution strategies between production, integration tests, and unit tests, many places across business code have to change.

**Dependency Injection (DI) via interface** establishes a clear boundary:

- **Business service:** depends only on the `TaskExecutor` contract and submits a `Runnable`.
- **Spring configuration:** decides which bean implements the contract: `ThreadPoolTaskExecutor`, `SyncTaskExecutor`, or another suitable implementation.
- **Spring container:** creates, injects, and manages the lifecycle of the involved beans.

The dependency direction should be:

```text
BusinessService  --depends on-->  TaskExecutor (interface)
                                    ^
                                    |
                       Spring injects a concrete bean
                         /                    \
            ThreadPoolTaskExecutor       SyncTaskExecutor
                 (pool)                     (same thread)
```

The key takeaway is **separating "what work to do" from "how the work is executed"**. Changing the implementation in the configuration layer does not force changes to processing logic inside the service.

## 2. What Does the `TaskExecutor` Contract Actually Guarantee?

`org.springframework.core.task.TaskExecutor` is a Spring interface extending Java's `java.util.concurrent.Executor`. Its core method:

```java
void execute(Runnable task);
```

When calling `execute(task)`, the caller asks the executor to run a `Runnable` according to the implementation's policy. The contract **does not promise** that the task always runs on another thread, runs immediately, runs in submission order, or is guaranteed to be accepted when the system is overloaded.

| Implementation | Notable execution behavior | Suitable when |
| --- | --- | --- |
| `ThreadPoolTaskExecutor` | Uses a configurable thread pool and queue; Spring manages lifecycle | Application needs a pool to handle many tasks |
| `SyncTaskExecutor` | Calls `Runnable.run()` directly on the current thread | Simple tests or intentionally synchronous execution |
| `SimpleAsyncTaskExecutor` | Normally creates a new thread per task without pool reuse; can configure virtual threads on supported platforms | Execution needs differ from traditional pooling |
| `ConcurrentTaskExecutor` | Adapter wrapping an existing Java `Executor` | Wanting to use an executor supplied externally |

One implementation may run *synchronously*, while another runs *asynchronously*. Therefore, the interface name `TaskExecutor` expresses **the ability to submit tasks**, not that every implementation is always asynchronous.

Do not confuse levels of abstraction:

- `TaskExecutor`: need the `execute(Runnable)` capability; does not directly return a result handle.
- `AsyncTaskExecutor`: extended interface adding the ability to submit tasks returning a `Future` (depending on method and API version); only depend on it if the service genuinely needs this feature.
- `TaskScheduler`: used to schedule execution at a specific time or on a recurring interval; this is a different purpose from submitting a task to run.
- JDK `Executor`: also has `execute(Runnable)`; can be used as the parameter type if Spring-specific contracts are not needed.

**Selection principle:** use the narrowest interface that satisfies the business requirement. A service that only "submits work" usually needs only `TaskExecutor`.

## 3. Runnable Example: One Service, Two Execution Strategies

The example below uses **Java 21, Spring Framework 6.2.1, and Maven**. The service depends on `TaskExecutor`; configuration selects the bean named `businessExecutor`. By default the application uses a pool; when the `sync` profile is enabled, it uses a synchronous executor. `MessageService` needs zero changes between the two modes.

### 3.1. Create the Project Structure

```text
executor-di-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ExecutorDiDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>executor-di-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                    <mainClass>example.ExecutorDiDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The Maven file defines the dependency required for Spring Context using Java 21-compatible source. Spring Boot is not needed to demonstrate constructor injection; Boot uses the exact same DI principle.

### 3.2. Complete Java Code

**File `src/main/java/example/ExecutorDiDemo.java`:**

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ExecutorDiDemo {
    public static final class MessageService {
        private final TaskExecutor executor;

        public MessageService(TaskExecutor executor) {
            this.executor = executor;
        }

        public CountDownLatch submit(String message) {
            CountDownLatch done = new CountDownLatch(1);
            executor.execute(() -> {
                try {
                    System.out.println("Processed: " + message);
                } finally {
                    done.countDown();
                }
            });
            return done;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("businessExecutor")
        @Profile("!sync")
        public ThreadPoolTaskExecutor pooledExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(32);
            executor.setThreadNamePrefix("business-");
            return executor;
        }

        @Bean("businessExecutor")
        @Profile("sync")
        public TaskExecutor syncExecutor() {
            return new SyncTaskExecutor();
        }

        @Bean
        public MessageService messageService(
                @Qualifier("businessExecutor") TaskExecutor executor) {
            return new MessageService(executor);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        String mode = args.length > 0 && "sync".equals(args[0])
                ? "sync" : "pool";
        try (var context = new AnnotationConfigApplicationContext()) {
            if ("sync".equals(mode)) {
                context.getEnvironment().setActiveProfiles("sync");
            }
            context.register(AppConfig.class);
            context.refresh();

            System.out.println("Mode: " + mode);
            CountDownLatch done =
                    context.getBean(MessageService.class).submit("M001");
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task timed out");
            }
            System.out.println("Completed: true");
        }
    }
}
```

### 3.3. Run and Verify

Run in the directory containing `pom.xml` with JDK 21+ and Maven:

```bash
mvn -q -DskipTests compile exec:java
```

Application output:

```text
Mode: pool
Processed: M001
Completed: true
```

Switch to the synchronous executor using the `sync` profile:

```bash
mvn -q -Dexec.args=sync exec:java
```

Application output:

```text
Mode: sync
Processed: M001
Completed: true
```

These outputs have been verified with Maven and compiled at the Java 21 language level. Maven/JVM may print additional environment messages when not run with `-q`.

**Why is the output order deterministic in this example?** The main thread waits on `CountDownLatch.await(...)`; the task prints the `Processed` line before calling `countDown()`. Even though the pooled run may process the task on another thread, the program only prints `Completed: true` after the latch is released.

`CountDownLatch` here only illustrates waiting for the task to finish. In real applications, a latch decremented in `finally` does not confirm business success; to receive values or errors, use an appropriate result-returning mechanism and exception handling.

## 4. Analyzing Why the Example Decouples the Implementation

### 4.1. The Service Knows Only the Interface

```java
private final TaskExecutor executor;

public MessageService(TaskExecutor executor) {
    this.executor = executor;
}
```

There is no `new ThreadPoolTaskExecutor()`, no knowledge of pool sizes, and no `instanceof` checks to decide how to run. All the service knows is that **it has an object accepting a `Runnable` to execute**.

In Spring, constructor injection makes dependencies explicit when instantiating the service, simplifies testing, and allows `final` fields. When a service has a single constructor, Spring can autowire it without needing `@Autowired` on the constructor.

### 4.2. Configuration Owns the Implementation

Both configuration methods declare a bean named `businessExecutor`, while `@Profile` conditions ensure only the matching configuration is activated:

- Profile `sync` not active → `pooledExecutor()` creates `ThreadPoolTaskExecutor`.
- Profile `sync` active → `syncExecutor()` creates `SyncTaskExecutor`.

The `messageService(...)` bean only asks for a parameter of type `TaskExecutor`. Spring resolves the compatible bean and injects it. The configuration layer owns the concrete class name and technical parameters.

In the pooled configuration, the concrete type is `ThreadPoolTaskExecutor` so `corePoolSize`, `maxPoolSize`, `queueCapacity`, and thread names can be configured. When Spring manages this bean, Spring invokes initialization and shutdown callbacks according to the context lifecycle. Never spin up and abandon an unmanaged thread pool inside a business service.

### 4.3. Why Is `@Qualifier` Needed?

In large applications, executors for sending emails, writing reports, handling events, and other tasks may coexist. If you inject only by `TaskExecutor` when multiple beans of that type exist, Spring may fail to disambiguate which bean to pick, or a `@Primary` bean may inadvertently be used for the wrong purpose.

```java
@Bean
public MessageService messageService(
        @Qualifier("businessExecutor") TaskExecutor executor) {
    return new MessageService(executor);
}
```

`@Qualifier("businessExecutor")` identifies the **role** of the executor without coupling the service to an implementation class. A business-meaningful bean name stays stable across configurations, while the implementation class can change.

If only one matching bean exists, a qualifier may not be required. When multiple beans exist, prefer qualifiers or clear naming to avoid accidentally swapping executors.

## 5. Testing Is Easier When Injecting an Interface

A major benefit of DI is the ability to test business logic **without creating pools, waiting on threads, or using `Thread.sleep`**.

Example using a fake executor that captures submitted `Runnable` instances. The snippet below is an illustrative test fragment; it uses `MessageService` from the example above and the corresponding Java imports:

```java
List<Runnable> submittedTasks = new ArrayList<>();
TaskExecutor fakeExecutor = submittedTasks::add;
ExecutorDiDemo.MessageService service =
        new ExecutorDiDemo.MessageService(fakeExecutor);

CountDownLatch done = service.submit("T001");

// Task has only been submitted to the fake executor, not yet executed.
if (submittedTasks.size() != 1 || done.getCount() != 1) {
    throw new AssertionError("Expected exactly one pending task");
}

submittedTasks.get(0).run(); // Test explicitly decides when to run.
if (done.getCount() != 0) {
    throw new AssertionError("Task did not finish");
}
```

Imports for this fragment: `java.util.List`, `java.util.ArrayList`, `java.util.concurrent.CountDownLatch`, and `org.springframework.core.task.TaskExecutor`.

This approach verifies **that the service submits exactly one task** and that task execution completes when the test explicitly calls `run()`. The test does not depend on thread scheduling. If a simpler sequential test is preferred, use `new SyncTaskExecutor()`.

Note that "testing that a task was submitted" is not equivalent to testing downstream side effects like successfully sending an email. Separate building the message/email content from the background dispatch mechanism so business outputs can be asserted independently.

## 6. Which Interface Should You Inject When?

Choose based on what **the business service actually uses**:

| Need | Suitable dependency | What not to assume |
| --- | --- | --- |
| Only submit a `Runnable` for execution | `TaskExecutor` or `Executor` | That the task definitely runs on another thread |
| Need the `submit(...)` API and a result handle | `AsyncTaskExecutor` or an executor type supporting `Future` | That every `TaskExecutor` has `submit` |
| Need tasks to run at a time or periodically | `TaskScheduler` | That `TaskExecutor` schedules itself |
| Need active count or queue size for monitoring | Configuration/monitoring component tied to the implementation, e.g., `ThreadPoolTaskExecutor` | That a business service should downcast from `TaskExecutor` |
| Want pure JDK compliance with no Spring API dependency | `java.util.concurrent.Executor` | Having to import Spring classes into business logic |

Do not inject `ThreadPoolTaskExecutor` into a service solely to call `execute()`. If a service has to call `getActiveCount()` or change `setCorePoolSize()` while handling requests, that is usually a sign of mixing business responsibilities with infrastructure monitoring/operations.

Never downcast like `((ThreadPoolTaskExecutor) executor).getActiveCount()` inside a service: switching the implementation to `SyncTaskExecutor` later will throw a `ClassCastException`. Specialized capabilities belong in configuration or dedicated infrastructure monitoring components.

## 7. How Does Injecting `TaskExecutor` Differ From Using `@Async`?

**Injecting a `TaskExecutor`** means business code explicitly submits a `Runnable` via `executor.execute(...)`. It operates according to the injected implementation and does not require `@Async`'s proxy mechanism.

**`@Async`** is a separate Spring mechanism that routes qualifying method calls to an executor. In plain Spring Framework configuration, `@EnableAsync` is usually required and the method must be called through a Spring proxy from outside the bean. Self-invocation via `this.someAsyncMethod()` normally bypasses the proxy and does not trigger `@Async` behavior under default proxy mode.

Illustrative example (requires `@EnableAsync` configuration and an appropriate Spring-managed bean, **not a standalone runnable snippet**):

```java
@Async("businessExecutor")
public void sendNoticeAsync(String id) {
    // Process notification payload.
}
```

`@Async("businessExecutor")` tells Spring to look up the executor by name; `@Qualifier("businessExecutor") TaskExecutor executor` is DI at the dependency declaration point. Both mechanisms can target the same bean, yet they differ in call path, lifecycle, and where exceptions are observed.

Likewise, `CompletableFuture.runAsync(runnable, executor)` accepts an `Executor`, but that interaction does not automatically make I/O inside the task non-blocking. A worker waiting on blocking JDBC/HTTP calls remains occupied for the entire wait duration.

## 8. Execution Boundaries That Still Need Management Despite Interface Decoupling

### 8.1. Thread Counts, Queues, and Overload

The illustrative configuration `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=32` is just example tuning, **not suitable defaults for every application**. With a `ThreadPoolTaskExecutor` backed by a positive-capacity queue, the pool normally fills core threads first and then queues tasks; only when the queue is full does it expand beyond core up to max. Therefore, setting a large `maxPoolSize` does not guarantee immediate scaling when tasks arrive in bursts.

When both pool and queue are full, `execute(...)` may be rejected with `TaskRejectedException` (per Spring's contract). The service must define an appropriate policy: fail with an error, retry with bounds, record a failed state, or use a durable queue if business rules require guaranteed delivery.

Measure `active threads`, `queue depth`, rejection rate, processing latency, and CPU usage when sizing pools; do not grow pools indefinitely to paper over slow downstream services.

### 8.2. Exceptions and Results

When using `execute(Runnable)` with an asynchronous implementation, exceptions thrown **inside a worker** do not automatically become exceptions rethrown on the calling thread. Separate two cases:

- **Errors at submission time:** may occur directly at `execute(...)`, such as overload rejection.
- **Errors during task execution:** must be logged/captured in the worker or handled via `Future`/`CompletionStage`, task monitoring, or business error reporting.

Do not report "processed successfully" merely because `execute(...)` did not throw an exception. That usually only indicates the executor accepted the task under the implementation's contract.

### 8.3. Transactions, Security, and ThreadLocal

When a task actually runs on another thread, do not assume values attached to the calling thread are carried over automatically. `ThreadLocal`, MDC logging, security context, or transaction context may be absent on the worker. A Spring transaction declared with `@Transactional` does not automatically span intact across a new thread just because the caller had an active transaction.

Design tasks to receive **required data** explicitly, bound execution time, apply intentional context propagation where needed, and place transaction boundaries where the work actually runs. You can use `TaskDecorator` or a suitable context-propagation solution for observability metadata, while avoiding copying mutable shared state across threads.

### 8.4. Thread Safety and Lifecycle

A Spring bean service is singleton by default, and multiple tasks may share the same instance. Code inside `Runnable` must protect shared state with proper synchronization or prefer immutable data. Injecting through an interface does not automatically make business logic thread-safe.

Let Spring manage the executor so initialization, shutdown, and lifecycle hooks run properly. On application shutdown, define whether pending/running tasks finish, cancel, or await termination according to configuration; never assume all background work is automatically flushed when the context closes.

## 9. Common Design Mistakes

1. **Injecting the concrete implementation into every service:** couples business code to pool configuration APIs; swapping executors forces edits in many places.
2. **Calling `new ThreadPoolTaskExecutor()` inside a service:** bypasses bean lifecycle management, easily forgets initialization or shutdown, and is hard to swap in tests.
3. **Assuming `TaskExecutor` is always async:** `SyncTaskExecutor` is a clear counterexample. If business logic strictly requires never blocking the caller, capture that requirement in design and test the real configuration.
4. **Having multiple `TaskExecutor` beans without disambiguating:** invites injection ambiguity or picking the wrong pool; use role-based names and `@Qualifier`.
5. **Relying on `maxPoolSize` while keeping a huge queue:** the pool may queue for a long time and fail to scale as imagined.
6. **Ignoring rejections or worker failures:** the service reports work was dispatched even though the task was rejected or failed internally.
7. **Assuming a new thread preserves request/transaction context:** drops correlation IDs, breaks authorization checks, or runs with incorrect transaction boundaries.
8. **Testing with `Thread.sleep` to wait for tasks:** tends to be slow and flaky; replace with a test executor, a bounded latch, or a result-bearing `Future`.
9. **Using a single pool for every workload type:** long I/O-bound tasks can monopolize workers and starve latency-sensitive tasks. Separate pools based on real workload needs and load measurements.

## 10. Checklist for Applying This in a Spring Project

Before introducing an executor into a service, answer:

- **Business contract:** does the service only need to submit a `Runnable`, or does it need a `Future`/result, scheduling, or guaranteed delivery?
- **Injection boundary:** do service fields and constructors use `TaskExecutor` (or `Executor`), or are they accidentally coupled to a pool class?
- **Bean identity:** is there a dedicated executor bean for the role, with consistent naming and explicit `@Qualifier` when multiple beans exist?
- **Runtime behavior:** in the current environment, does the executor run synchronously or asynchronously, and how can its pool/queue saturate?
- **Testability:** can it be swapped for `SyncTaskExecutor` or a fake executor and tested without timing dependencies?
- **Operations:** are timeouts, exceptions, rejections, propagation, shutdown, and metrics handled at the appropriate layers?

A maintainable layering pattern is **the business service says "execute this task" via an interface; configuration says "execute it this way" via an implementation**. This keeps business logic stable when moving from synchronous execution in tests to a thread pool at runtime or swapping executors later.

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)