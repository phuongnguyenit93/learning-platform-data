# Specifying an Executor by Name or Qualifier in @Async

## 1. Goal: One Spring Application, Multiple Workload Groups

In the Spring Framework, `@Async` allows a Spring bean method to be invoked through an asynchronous execution mechanism. Instead of running the entire method body immediately on the calling thread, Spring can dispatch the invocation to an `Executor`/`TaskExecutor`. When an application has only one category of work, a single default executor configuration is sometimes enough. In real-world systems, however, different task groups have very different profiles:

- **I/O-bound:** calling APIs, reading data, sending notifications; external wait times can be large.
- **CPU-bound:** computation, data transformation; having more workers than CPU capacity rarely helps.
- **Latency-sensitive tasks:** updating user state, fast responses.
- **Long background tasks:** rendering reports, file processing, work that can tolerate longer waits.

If everything shares a single pool, long-running tasks can occupy workers or fill the queue, forcing critical tasks to wait. Therefore, you should **route each `@Async` method to the right executor**, using a **bean name** or **qualifier**.

Design intent example:

```text
                 Spring-managed service
                         |
             +-----------+-----------+
             |                       |
      @Async("ioExecutor")    @Async("computeLane")
             |                       |
             v                       v
       Executor A                Executor B
       io-worker-*               cpu-worker-*
       I/O wait                  CPU work
       dedicated queue           dedicated queue
```

**Syntax to know:**

```java
@Async("ioExecutor")
public CompletableFuture<String> fetchData() {
    // Runs on the executor matching the name "ioExecutor".
    return CompletableFuture.completedFuture("done");
}
```

This is a **Spring method fragment**, not a standalone Java program. The string `"ioExecutor"` sits in `@Async`'s `value` attribute. Spring uses it to look up a matching executor bean by **bean name or qualifier**, not to create a new pool and not as a thread name.

Expected takeaways from this lesson: you understand how to declare multiple executors, select by bean name/qualifier, prioritize method annotations over class annotations, specify executor selection via properties, avoid proxy/self-invocation bugs, and test that routing actually works.

## 2. Prerequisites for @Async to Take Effect

Writing `@Async("...")` on a method alone is **not enough**. In Spring's proxy model, you generally need:

1. `@EnableAsync` on a `@Configuration` class belonging to the appropriate `ApplicationContext`, or equivalent annotation-driven configuration.
2. The object containing the method must be a **Spring-managed bean**, not an object manually created with `new` and called directly by business code.
3. The call must pass **through the Spring proxy**, for example another bean injecting the service and calling the method.
4. The method must have a signature supported by `@Async`: typically `void`, `Future<T>`, or `CompletableFuture<T>`; do not declare an arbitrary return type like `String` expecting Spring to convert it automatically.
5. The designated executor must be a real, compatible `Executor`/`TaskExecutor` bean discoverable by Spring.

A proper proxy-routed call:

```text
Bean A (caller)
  -> Bean B's proxy
      -> @Async interceptor
          -> resolve Executor by value
              -> execute/submit task
                  -> worker invokes Bean B's method body
```

If Bean B calls `this.asyncMethod()` inside itself, the call bypasses the Spring proxy in default mode and the method body usually runs synchronously on the caller. In that case, even if `@Async("ioExecutor")` syntax is completely valid, **no routing to the executor** occurs as expected.

Spring documentation explicitly notes that `@EnableAsync` activates processing only within the **local application context**. In multi-context applications (such as separate root and servlet contexts), place configuration in the exact context managing the beans.

## 3. @Async("name"): Selecting an Executor by Bean Name

The most direct approach is declaring an executor bean with an explicit name:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExecutorConfiguration {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("io-worker-");
        return executor;
    }
}
```

This is a **Spring configuration class** requiring Spring Framework dependencies. It has no `main` method. When Spring creates the bean, its registered name is `ioExecutor`. An asynchronous method elsewhere can reference that exact name:

```java
@Async("ioExecutor")
public CompletableFuture<String> callRemoteApi(String id) {
    // Illustrative code; performs no real network call.
    return CompletableFuture.completedFuture("fetched-" + id);
}
```

Key point: **the name inside `@Async` must match a registered bean name or qualifier**. If you declare `@Bean("ioExecutor")` but write `@Async("io-worker-")`, Spring does not deduce the executor from the thread name prefix. Thread prefixes only help observe workers in logs/thread dumps.

`@Async("ioExecutor")` and `@Async(value = "ioExecutor")` mean the exact same thing: `value` is the annotation attribute, and the attribute name can be omitted when providing a single value.

**Do not confuse the bean name with the configuration method name.** With:

```java
@Bean("ioExecutor")
public ThreadPoolTaskExecutor makeIoPool() { /* ... */ }
```

The assigned bean name is `ioExecutor`, even though the Java method is named `makeIoPool`. With `@Bean` given no name argument, the method name typically becomes the default bean name; prefer explicit names when using them for `@Async` routing.

## 4. @Async("qualifier"): Selecting by @Qualifier Label

Spring allows tagging an executor bean with a qualifier. `@Async` can use the **qualifier value** as the lookup key, even when the bean itself carries another name.

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ComputePoolConfiguration {

    @Bean("computeExecutor")
    @Qualifier("computeLane")
    public ThreadPoolTaskExecutor computeExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("cpu-worker-");
        return executor;
    }
}
```

On the service side:

```java
@Async("computeLane")
public CompletableFuture<Integer> calculate(int input) {
    return CompletableFuture.completedFuture(input * 2);
}
```

In this case:

| Element | Value | Role |
|---|---|---|
| `@Bean("computeExecutor")` | `computeExecutor` | Actual bean name in the container |
| `@Qualifier("computeLane")` | `computeLane` | Qualifier label attached to the executor bean definition |
| `@Async("computeLane")` | `computeLane` | Tells Spring to pick the executor with this qualifier |
| `setThreadNamePrefix("cpu-worker-")` | `cpu-worker-` | Prefix for naming worker threads; **not** used for bean selection |

**A qualifier is not a separate executor.** Using a qualifier only changes how the bean is identified, while thread/queue resources still belong to the registered executor instance. This is useful when you want to keep legacy bean names stable for existing wiring while giving business-meaningful labels to `@Async` methods.

A qualifier can express a logical role, such as `computeLane`, `reporting`, or `notifications`, rather than coupling business methods to concrete implementation names. However, never attach the same qualifier to multiple equivalent executors and reference that value in `@Async`: if resolution cannot narrow down to a unique bean, it can fail due to ambiguity.

### 4.1. Where Does @Qualifier Matter?

Using `@Qualifier` to select a bean at an **injection point**:

```java
public MyService(@Qualifier("computeExecutor") Executor executor) {
    this.executor = executor;
}
```

does not mean all `@Async` methods in `MyService` automatically use that executor. `@Async` has its **own** executor selection mechanism via `value`, the default executor, or `AsyncConfigurer`.

To select via qualifier in the annotation, attach the qualifier **to the executor bean definition** and write `@Async("computeLane")` on the target method, as shown above. Do not place `@Qualifier` on an unrelated parameter assuming it overrides `@Async`.

## 5. Complete Runnable Example With Java 17 + Spring Framework

This example intentionally uses **two separate executors**. One method selects by **bean name** and the other selects by **qualifier**, then prints the actual executing thread names to prove routing.

This is a minimal Maven project running on **JDK 17+** with **Spring Framework 6.2.7**. Use the exact dependencies/versions in the example `pom.xml`; for real applications, choose versions matching your project's BOM/stack.

### 5.1. Directory Structure

```text
async-routing-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── lesson/
                └── AsyncRoutingDemo.java
```

### 5.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lesson</groupId>
    <artifactId>async-routing-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the Spring components used in this lesson; Maven resolves transitive dependencies from metadata. The example uses **default `@EnableAsync` proxy mode**, requiring no additional AspectJ weaving setup.

### 5.3. File src/main/java/lesson/AsyncRoutingDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncRoutingDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            // Always retrieve the service from Spring so calls go through the proxy.
            WorkService service = context.getBean(WorkService.class);

            String ioThread = service.readFromIo().join();
            String cpuThread = service.calculate().join();

            System.out.println("I/O executor: " + ioThread);
            System.out.println("CPU executor: " + cpuThread);
        }
    }

    @Configuration
    @EnableAsync
    public static class Config {

        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("io-worker-");
            return executor;
        }

        @Bean("cpuExecutor")
        @Qualifier("computeLane")
        public ThreadPoolTaskExecutor cpuExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("cpu-worker-");
            return executor;
        }

        @Bean
        public WorkService workService() {
            return new WorkService();
        }
    }

    public static class WorkService {

        // Select executor by bean name.
        @Async("ioExecutor")
        public CompletableFuture<String> readFromIo() {
            String thread = Thread.currentThread().getName();
            return CompletableFuture.completedFuture(thread);
        }

        // Select executor by qualifier, not bean name.
        @Async("computeLane")
        public CompletableFuture<String> calculate() {
            String thread = Thread.currentThread().getName();
            return CompletableFuture.completedFuture(thread);
        }
    }
}
```

### 5.4. Running and Reading the Output

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.AsyncRoutingDemo
```

Two lines printed by the program on a successful run:

```text
I/O executor: io-worker-1
CPU executor: cpu-worker-1
```

Maven may print additional tool output if run options are changed. Those **two lines above** are the output from `System.out.println` in the program.

Why are the thread names predictable in this minimal example?

- Both pools are created independently, and each pool executes only **one task** during the entire run.
- Spring uses the configured prefix when creating the first worker of each pool, yielding `io-worker-1` and `cpu-worker-1`.
- The program retrieves the service from `ApplicationContext`, so calls pass through the `@Async` proxy.
- `join()` runs on the main thread to wait for each result **strictly to verify the example**; the method bodies execute on workers of their respective executors.
- The methods return `CompletableFuture.completedFuture(...)` inside the workers because target methods must match the return type. The Spring proxy returns a `CompletableFuture` representing the asynchronous execution.

**Do not copy calling `join()` immediately in every HTTP request** assuming the endpoint stays fully asynchronous: the request thread will block waiting. In real applications, callers can return the future, attach callbacks, or coordinate results non-blockingly per upper-layer contracts.

This example performs no real HTTP calls or heavy computation. It **verifies routing paths** between methods and executors, not I/O or CPU benchmarking.

## 6. How Do Bean Name, Qualifier, and Thread Name Differ?

These three concepts are completely distinct:

| Property | Who Uses It? | Example | What Happens If Changed? |
|---|---|---|---|
| Bean name | Spring IoC/lookup | `ioExecutor` | `@Async("ioExecutor")` calls may no longer find the bean |
| Qualifier | Spring IoC selecting a bean by label | `computeLane` | Calls selecting by that qualifier must be updated too |
| Thread name prefix | Executor naming worker threads | `cpu-worker-` | Only changes worker thread names; does not alter bean selection |
| Java method name declaring bean | Java/Spring bean creation | `cpuExecutor()` | If `@Bean` has an explicit name, renaming the method does not necessarily change bean name |
| `@Async` method name | Business / proxy method | `calculate()` | Does not determine executor name |

Never infer the executor from thread names: seeing `cpu-worker-1` in logs does not mean a bean is named `cpu-worker-1`. Conversely, an executor bean named `reportingExecutor` can configure thread prefix `report-` while still being targeted with `@Async("reportingExecutor")`.

When naming, prefer describing **workload group** or **resource role**: `ioExecutor`, `reportExecutor`, `mailExecutor`, `computeLane`. Avoid encoding implementation sizing like `poolWithEightThreads` in the bean name, as later size tuning makes the name misleading.

## 7. Class-Level @Async and Method-Level Precedence

`@Async` can be declared on both **classes** and **methods**. When placed on a class, eligible methods in the class become candidates for asynchronous processing. A method with `@Async` specifying a concrete `value` **takes precedence over the executor specified on the class**.

Example:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
@Async("ioExecutor")
public class MixedWorkService {

    public CompletableFuture<String> fetch() {
        return CompletableFuture.completedFuture("I/O");
    }

    @Async("computeLane")
    public CompletableFuture<String> transform() {
        return CompletableFuture.completedFuture("CPU");
    }
}
```

This is a **Spring component** with no standalone `main` program; it assumes executor `ioExecutor` and qualifier `computeLane` already exist.

| Method | Selected Executor | Why |
|---|---|---|
| `fetch()` | `ioExecutor` | Uses class-level `@Async("ioExecutor")` configuration |
| `transform()` | `computeLane` | Method-level `@Async("computeLane")` overrides class selection |

**Do not view class-level annotation as a way to change the application-wide default executor**: it applies only within the annotated class. To set a shared default for `@Async` methods without `value`, configure the default executor via `@EnableAsync`/`AsyncConfigurer` or equivalent configuration.

Use class-level `@Async` when most methods in a service genuinely belong to the same workload group. If only one or two methods need async execution, method-level placement is usually easier to control: it avoids accidentally turning other methods async, especially when new methods are added later.

Note from the `@Async` Javadoc: do not apply this annotation to methods declared inside a `@Configuration` class. Place business methods in a separate service/component and keep configuration solely for declaring resources.

## 8. When the Annotation Has No value, What Changes?

An unqualified `@Async` uses the context's default executor: potentially returned by `AsyncConfigurer`, resolved by Spring Framework looking up a single selectable `TaskExecutor`, then an `Executor` bean named `taskExecutor`, or falling back when no candidate matches. Spring Boot can also pre-supply an executor via auto-configuration. Thus there are two distinct paths:

```java
@Async                    // Default, depends on context configuration.
public CompletableFuture<String> generalJob() {
    return CompletableFuture.completedFuture("general");
}

@Async("ioExecutor")       // Explicitly specifies bean/qualifier.
public CompletableFuture<String> ioJob() {
    return CompletableFuture.completedFuture("io");
}
```

These are illustrative methods in a Spring service, not a standalone Java file. When SLAs must be controlled per workload group, methods with specific requirements should use explicit qualifiers and be tested in a real context; `@Primary` or arbitrary bean names do not replace routing proof.

## 9. Selecting Executor Names via Property Placeholder or SpEL

The `Async.value` Javadoc allows providing a **property placeholder** or **SpEL expression** instead of hard-coding a bean name. This is useful for switching routes per deployment environment without editing annotations.

### 9.1. Property Placeholder

Suppose the Environment configuration contains:

```properties
app.async.report-executor=ioExecutor
```

The service can be written as:

```java
@Async("${app.async.report-executor}")
public CompletableFuture<String> createReport(String id) {
    return CompletableFuture.completedFuture(id);
}
```

In the code above, the string starts with a **dollar sign and curly braces** per Spring property placeholder syntax. When Spring resolves it to `ioExecutor`, the executor bean with that name is selected. This is a **Spring method fragment** requiring the appropriate property source, context, and executor bean.

In Spring Boot, the property can be declared in `application.properties`, environment variables, or compatible configuration mechanisms; in plain Spring Framework, configure the appropriate property source/Environment. If the property fails to resolve or its value points to a nonexistent bean, routing can fail—it should not silently substitute another executor.

### 9.2. SpEL

The name can be resolved via Spring Expression Language:

```java
@Async("#{environment['app.async.report-executor']}")
public CompletableFuture<String> createReport(String id) {
    return CompletableFuture.completedFuture(id);
}
```

The property value in the example remains `ioExecutor`. Javadoc notes that `@Async.value` is dynamically resolved when given SpEL or a placeholder; this does not mean it is an arbitrary expression that can depend directly on any method parameter without appropriate context design.

**Which should you choose?**

- Fixed name `@Async("ioExecutor")`: easy to read and catches misconfigurations quickly.
- Placeholder `@Async("${app.async.report-executor}")`: suitable when selecting names per environment or deployment config.
- SpEL: suitable when clearer resolution logic is needed, though expressions should remain simple and easy to test.

If you need to switch executors **per request or per tenant** at runtime, do not assume placeholders/SpEL make a full dynamic task dispatcher. Implement the routing policy in a service or dedicated abstraction rather than turning annotations into hard-to-govern logic.

## 10. Distinguishing @Qualifier for Injection From @Async Qualifiers

Consider this service:

```java
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;

public class ConfusingService {
    private final Executor executor;

    public ConfusingService(
            @Qualifier("ioExecutor") Executor executor) {
        this.executor = executor;
    }

    @Async("computeLane")
    public void process() {
        System.out.println("Processing");
    }
}
```

This is an illustrative class that must be registered as a Spring bean for `@Async` to take effect.

Exact meaning:

- `@Qualifier("ioExecutor")` on the constructor selects the bean assigned to the **`executor` field**.
- `@Async("computeLane")` on `process()` instead asks **`computeLane`** to run the method body.
- The `executor` field is never even called in `process()`; the constructor qualifier does **not** force `@Async` to use `ioExecutor`.

These are two separate mechanisms despite sharing the word "qualifier." If a service both submits manually through a field and uses `@Async`, having two different execution paths is very easy. Use consistent names, document each pool's purpose, and write tests distinguishing them.

### 10.1. Can Executor Be Used Instead of TaskExecutor?

Yes. The `Async.value` Javadoc mentions matching beans of type `java.util.concurrent.Executor` **or** `org.springframework.core.task.TaskExecutor`. Because `TaskExecutor` extends `Executor`, a Spring `ThreadPoolTaskExecutor` satisfies both.

You can also register an `Executor` supplied by another library for Spring to use, but you must clarify pool ownership, lifecycle, and rejection policies. Never let an individual child service shut down a shared resource pool.

In Jakarta EE, `DefaultManagedTaskExecutor` can be registered as a Spring bean delegating to a managed executor via JNDI. `@Async("managedExecutor")` selects that named Spring bean, while worker management is handled by the Jakarta EE server. That is simply another executor choice and does not change the meaning of `value`.

## 11. Right Executor Name Specified, Yet Method Still Not Routed?

In the default `AdviceMode.PROXY`, bean name/qualifier resolution only occurs when calls pass **through the Spring-managed proxy**. If the same bean calls `this.runInBackground()`, or the object is manually instantiated with `new`, the async interceptor never runs. `private`/`final` methods and code in constructors/lifecycle callbacks are also unsuitable interception targets for ordinary proxies; `@Async` is not supported on methods declared inside `@Configuration`.

To separate the two error classes, first verify that the context has `@EnableAsync`, the bean is Spring-managed, and the public/non-final method is called from another bean. Next, inspect the `Executor` bean matching the `@Async("...")` name or qualifier. If the call reached the proxy but the name is wrong or the qualifier is ambiguous, execution fails during executor lookup; if the pool is full, submission can be rejected. Changing `proxyTargetClass` does not fix a misspelled bean name or make private/final methods valid interception points.

Whenever renaming `@Bean("ioExecutor")` or `@Qualifier("computeLane")`, find all referencing `@Async` methods and rerun integration tests for both pools. Use thread prefixes to observe, but never treat thread names as business data.

## 12. Results and Exceptions Once Properly Routed

Choosing the right executor only solves **where work executes**. Callers and services still must manage results, errors, deadlines, and business state.

### 12.1. Methods Returning void

```java
@Async("ioExecutor")
public void sendNotification(String id) {
    // Runs on the selected executor; no result for the caller.
}
```

If the method body throws an exception on the worker, the caller has no `Future` to catch it directly. Spring provides `AsyncUncaughtExceptionHandler` for exceptions from `void`-returning `@Async` methods; default behavior logs them. Errors occurring **before the task is accepted** (such as executor rejection) are a separate case to handle at the submission boundary.

### 12.2. Methods Returning CompletableFuture

```java
@Async("computeLane")
public CompletableFuture<Integer> twice(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("x must be non-negative");
    }
    return CompletableFuture.completedFuture(x * 2);
}
```

When called **through a Spring proxy**, the caller receives a `CompletableFuture<Integer>` representing async execution. If worker code throws `IllegalArgumentException`, the caller's future completes exceptionally; the caller can attach `exceptionally(...)`, `handle(...)`, or observe the exception via `join()/get()`.

Example:

```java
CompletableFuture<Integer> future = service.twice(-1);
future.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Task failed: " + error);
    }
});
```

This is a **caller snippet** assuming `service` is injected/retrieved from Spring; not a standalone runnable program. Calling `join()` or `get()` can block the caller, which must be weighed carefully on HTTP request threads.

### 12.3. Errors When the Executor Is Overloaded

`ThreadPoolTaskExecutor` can reject new tasks when workers/queues are full or the pool is closed. With standard `AbortPolicy`, Spring surfaces rejection as `TaskRejectedException` at submission time. That does not mean the business method ran and failed.

Two distinct error phases:

| Timing | Example | Where to Handle |
|---|---|---|
| Executor resolution/selection | `@Async("missingPool")`, wrong name, or ambiguous qualifier | Fix config, bean names, and test wiring |
| Task submission | Pool shut down or overloaded | Caller or request boundary: backpressure, proper error/retry |
| Task execution | Exception from logic inside `@Async` | `Future/CompletableFuture`, or `AsyncUncaughtExceptionHandler` for `void` |
| Task finishes too late | Request deadline expired or result is stale | Timeouts, cancellation, deadline checks, and idempotency |

Never swallow a rejection exception and still return "processed" to the user. `@Async` is not a durable message broker: if the JVM crashes, tasks sitting only in an in-memory queue can be lost.

## 13. Size Pools by Workload Characteristics, Not Just by Name

Routing helps only when pools are designed around workload behavior.

| Group | Examples | Considerations |
|---|---|---|
| I/O-bound | HTTP, database, RPC | Connection limits, timeouts, downstream capacity, worker count |
| CPU-bound | Number crunching, compression, transforms | Core count, CPU quota, contention, avoid over-subscription |
| Short yet critical | Fast status updates | Queuing and p95/p99 latency; must not be blocked by long jobs |
| Long background work | Reporting, file processing | Bounded queues, retry capability, persistent jobs if needed |

Having two separate pools does not mean total isolation. They still share CPU, heap, GC, databases, networks, and external system capacity. If two pools compete over one small connection pool, executor-level isolation does not isolate downstream capacity.

`corePoolSize`, `maxPoolSize`, and `queueCapacity` must be tuned together. With the `ThreadPoolExecutor` backing `ThreadPoolTaskExecutor`, once core workers are busy, tasks normally queue before expanding workers up to max. An overly large queue can leave `maxPoolSize` virtually unused; an overly small queue can trigger rejections during bursts.

**How to measure and verify:**

- Split logs/metrics by **executor name**: submitted, active, queued, completed, rejected.
- Inspect `getPoolSize()`, `getActiveCount()`, and queue size using APIs/monitoring supported by your Spring version.
- Measure time from submission to worker start, p95/p99 latency, and execution duration.
- Monitor connection pools, CPU, heap, GC, and upstream retries.
- Apply concurrency limits or rate limits when submission exceeds processing capacity; growing the queue adds latency, not throughput.
- Choose a shutdown policy: whether new tasks are rejected, how active tasks finish, and whether queued tasks complete or cancel.

Never create a new pool on every `@Async` call, and never call `shutdown()` on a shared executor bean from an individual service. Let Spring/the container manage bean lifecycles; business code is responsible for controlled submission and observing outcomes.

## 14. ThreadLocal, Security Context, and Transactions Do Not Follow Executors Automatically

An executor properly selected via `@Async("ioExecutor")` does not mean calling-thread data automatically exists on the worker:

- Custom `ThreadLocal`s and MDC logging are normally bound to the calling thread.
- `SecurityContextHolder` and Spring request context require explicit propagation if the task truly needs them.
- Spring transactions are typically thread-bound; an `@Async` method running on a worker **does not automatically join the caller's transaction**.
- An `EntityManager`, JDBC connection, or request object has its own lifecycle; do not pass those objects to workers for arbitrary use.

If a task needs `correlationId`, `tenantId`, or identity info for processing, pass the **necessary immutable data** via arguments or use a verified context-propagation mechanism. If the task needs a transaction, establish a new transaction on an appropriate execution boundary.

Important: selecting an executor is a **task-routing decision**, not a substitute for transaction, security, context propagation, or durability guarantees.

## 15. Verifying Executor Selection in Tests

At a minimum, include an integration test running with a real `ApplicationContext`:

1. Initialize the context with `@EnableAsync` and both executors.
2. Retrieve the service from Spring; do not `new` it directly.
3. Call both the `@Async("ioExecutor")` method and `@Async("computeLane")` method.
4. Observe thread names/pool metrics or execution markers; verify each method lands on its intended pool.
5. Use `CompletableFuture`/`CountDownLatch` for bounded waiting in async tests; never use `Thread.sleep(...)` assuming tasks finished.
6. Test a deliberately wrong qualifier in a test case to understand lookup errors; then restore the valid name.
7. Test self-invocation to verify why the annotation can fail to apply.
8. Test controlled overload and verify rejection is surfaced properly.

### 15.1. Why Isn't Checking @Bean Existence Enough?

`context.containsBean("ioExecutor")` only proves a bean with that name exists. It **does not prove** the `@Async` method was proxied or actually uses that bean. The right bean can exist while calls via `this` lose interception.

Conversely, seeing two different thread names is not enough in a large system: threads could come from another pool sharing a prefix. `AsyncRoutingDemo` sets two distinct prefixes in isolation so it suffices for learning the principle; in production, combine bean wiring inspection, pool metrics, and targeted tests.

### 15.2. Do Not Turn Thread Names Into Business Contracts

Thread names are useful for debugging or sample tests, not as **APIs guaranteeing business outcomes**. Users do not care whether a task ran on `io-worker-1` or `io-worker-3`; they care that work was accepted, can be tracked, and errors are handled.

If production tests depend on exact thread numbers, they become brittle when pool sizes grow or thread factories change. Tests should prove tasks reach the **right logical executor**, not pin an irrelevant thread ID.

## 16. Using Qualifiers From XML and Mixed Setups

Older Spring projects may configure executors and qualifiers in XML. The principle matches Java Configuration: `@Async.value` can look up by bean name or qualifier attached to an executor.

**Illustrative** XML snippet inside a Spring XML file with valid `beans`/`task` namespaces declared:

```xml
<bean id="computeExecutor"
      class="org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor">
    <qualifier value="computeLane"/>
    <property name="corePoolSize" value="2"/>
    <property name="maxPoolSize" value="2"/>
    <property name="queueCapacity" value="8"/>
</bean>
```

`@Async("computeLane")` can then use that label for selection. If XML configures a default annotation-driven executor, that is the default setting; it does not override explicit selections on methods with `@Async("...")`.

When an application mixes Java Configuration, XML, Spring Boot auto-configuration, and profile-conditional configs, bean name or qualifier collisions easily happen. List **the `Executor` beans actually present at runtime** under the active profiles rather than guessing from a single config file.

## 17. Common Mistakes

| Symptom | Possible Cause | How to Check and Fix |
|---|---|---|
| `@Async("ioExecutor")` yet method runs on request thread | Self-invocation, manually `new`-ed object, missing `@EnableAsync` | Call through bean proxy; check ApplicationContext |
| `ioExecutor` not found | Typo in name or bean excluded by profile/condition | Verify actual bean name, namespace/context |
| `@Async("cpu-worker-")` fails to find pool | Used thread prefix instead of bean name/qualifier | Use `@Bean("computeExecutor")` or `@Qualifier("computeLane")` |
| `@Async("computeLane")` fails to pick bean | Qualifier missing on executor bean, or ambiguous | Attach qualifier to bean properly and ensure unique resolution |
| Constructor injects `@Qualifier("ioExecutor")` yet `@Async` uses another pool | Confusing injection qualifier with `@Async.value` | Specify executor directly on the method |
| `@Async` on class yet an important method enters wrong pool | No method-level override declared | Use `@Async("otherExecutor")` on methods needing another pool |
| Unqualified `@Async` assumed to pick an arbitrary bean | Default selection differs from expectation | Configure `AsyncConfigurer` or use explicit names |
| Changing property holding pool name stops task from running | Unresolved placeholder, wrong target name | Check Environment and bean names/qualifiers |
| Annotated method returns `String` | Invalid return type for standard async processing | Use `void`, `Future`, or `CompletableFuture` |
| Exception from `void` method never reaches caller | No return channel | Configure `AsyncUncaughtExceptionHandler` or change API |
| Future fails yet nobody notices | No completion handling | Use `whenComplete`, `handle`, or monitoring |
| Task rejected when queue fills | Pool overloaded or shut down | Design backpressure, handle `TaskRejectedException` |
| Context/security/transaction missing | New thread does not carry all contexts by default | Pass info explicitly and open appropriate transactions |
| Annotation on `@Bean` config method | `@Async` not supported on methods in `@Configuration` | Move work to a Spring-managed service |

## 18. Practice Exercises

### Exercise 1 — Selecting by Bean Name

Declare two `ThreadPoolTaskExecutor` beans named `imageExecutor` and `mailExecutor`. Write two corresponding methods `resizeImage(...)` and `sendMail(...)` using `@Async` so each enters its own pool.

**Guidance:** Use `@Bean("imageExecutor")`/`@Bean("mailExecutor")`, then `@Async("imageExecutor")` and `@Async("mailExecutor")`. Verify `@EnableAsync` and calls through the proxy.

### Exercise 2 — Selecting by Qualifier

A bean is named `batchPool` with qualifier `reports`. Write `generateReport()` routing by qualifier without renaming the bean.

**Guidance:** Declare `@Bean("batchPool")` and `@Qualifier("reports")` on the bean definition, and `@Async("reports")` on the method. A qualifier on another component's constructor injection does not automatically assign a qualifier to the bean.

### Exercise 3 — Class/Method Precedence

A class annotated with `@Async("ioExecutor")` has two methods `fetch()` and `compute()`; `compute()` also declares `@Async("computeLane")`. When called through a proxy, which method uses which pool?

**Guidance:** `fetch()` uses the class-specified executor; `compute()` uses the method-specified executor.

### Exercise 4 — Switching Names via Configuration

Configure `app.async.report-executor=ioExecutor` and `@Async("${app.async.report-executor}")`. When changing the property to `computeExecutor`, what must be verified?

**Guidance:** An executor bean named `computeExecutor` must exist, the property must resolve properly in the context, and the workload must suit the new pool. Changing the value does not automatically resize the pool or guarantee resource isolation.

### Exercise 5 — Finding a Self-Invocation Bug

A bean's synchronous `start()` method calls `this.doAsync()`, even though `doAsync()` has `@Async("ioExecutor")`. Why is it observed still running on the caller thread?

**Guidance:** The call does not pass through the proxy. Extract the async method to another bean and inject/call it through Spring.

### Exercise 6 — Running the Maven Project

Run `AsyncRoutingDemo` from section 5 and verify the two lines have different prefixes. Then change `@Async("computeLane")` to `@Async("ioExecutor")` and predict the second line.

**Guidance:** Both calls will select the same `ioExecutor` bean; in the example setup with one worker used sequentially, the second line's prefix will be `io-worker-`. This is a routing change, not a change to method names or computed data.

### Exercise 7 — Specify Executor or Tune Pool?

A team routes `@Async("reporting")` correctly, yet the reporting queue keeps growing nonstop. Should they increase `maxPoolSize` or `queueCapacity` first?

**Guidance:** Never decide from the executor name alone. Measure queue wait, throughput, execution duration, downstream limits, and memory. If the queue is long, enlarging the queue usually increases wait times; if the pool is already stalled on downstream calls, adding workers may worsen contention. Address input limits and SLAs before tuning numbers.

## 19. Project Application Checklist

When a PR adds or modifies `@Async("...")`, check:

1. **Name/qualifier:** The string in the annotation matches the exact bean name or qualifier of an existing `Executor`/`TaskExecutor`.
2. **Bean registration:** The executor bean is active in the needed ApplicationContext and active profiles.
3. **Async enabled:** `@EnableAsync`/equivalent configuration is applied in the right context.
4. **Call path:** Method is public, non-final (in standard proxy designs), and called via proxy rather than `this`.
5. **Precedence:** Method-level annotations are intentional relative to class-level/default choices.
6. **Results:** Return type `void/Future/CompletableFuture` fits tracking needs; errors have an observation channel.
7. **Resources:** Workers/queues are bounded, suited to the workload, and have a rejection policy.
8. **Context:** Any request/security/transaction info needed on the worker is handled properly.
9. **Lifecycle:** Pools are not created/shut down per request; application shutdown behavior is understood.
10. **Testing:** Evidence of routing through the Spring proxy and executor-level monitoring, not just checking bean existence.

## 20. Conclusion

- **`@Async("beanName")` selects an executor bean by name** registered with Spring.
- **`@Async("qualifier")` can also select an executor by qualifier** such as `@Qualifier("computeLane")` attached to the bean definition.
- `@Async.value` is not a thread name, not an arbitrary class name, and does not create a new pool automatically.
- **Method-level selection takes precedence over class-level**, while methods specifying no executor use the appropriate default configuration.
- `@EnableAsync` and **calls passing through a Spring proxy** are fundamental requirements for routing to take effect in default proxy mode.
- Picking the right pool is not enough: you must manage **results/errors, resources, context, transactions, and overload** as part of application responsibility.
- Use **an integration test with two executors** like the Maven example to prove methods actually reach their designated pools.

### Official Documentation

- [Spring Framework Javadoc — Async](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework Javadoc — EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework Javadoc — AsyncConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
