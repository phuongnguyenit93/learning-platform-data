# How Spring Resolves a TaskExecutor or taskExecutor Bean When None Is Explicitly Configured

> **Module:** Spring Framework – concurrency  
> **Parent Topic:** Enabling @Async  
> **Objective:** Precisely explain which `Executor` Spring selects for an `@Async` method that does not specify an executor name when the application provides no `AsyncConfigurer.getAsyncExecutor()`; distinguish **bean type** lookup, **bean name** lookup, the fallback executor, and Spring Boot auto-configuration.

## 1. Direct Answer

In the Spring Framework, once `@Async` processing is activated (typically via `@EnableAsync`), if a method is invoked **through a Spring proxy**, specifies no qualifier in `@Async`, and has no explicitly configured default executor, the async processor looks up an executor in this order:

1. **Look for a uniquely resolvable `TaskExecutor` bean by type in the `ApplicationContext`.** If one is found, use that bean, even if the bean name is not `taskExecutor`.
2. **If step 1 does not select one, look for a bean named exactly `taskExecutor` of type `java.util.concurrent.Executor`.** If found, use that bean. A `ThreadPoolTaskExecutor` bean is also valid here because it implements both interfaces.
3. **If neither resolves, Spring uses a local fallback `SimpleAsyncTaskExecutor`** to execute the `@Async` call.

The decisive point is **type lookup first, name lookup second**. Merely having some bean named `taskExecutor` does not mean it always beats every other `TaskExecutor`; nor is every arbitrary `Executor` automatically chosen.

The rule above is documented in the official Javadoc of `@EnableAsync` and `AsyncExecutionAspectSupport`. It governs the **default executor for `@Async` processing in the Spring Framework**; other integrations such as Spring MVC async requests or WebFlux may use their own executor selection rules.

## 2. Conditions for This Mechanism to Actually Apply

Before discussing executor selection, there must be an `@Async` call intercepted by Spring:

~~~java
@Configuration
@EnableAsync
class AsyncSupportConfiguration {
}
~~~

This is an **integration Spring configuration snippet**, requiring imports for `@Configuration` and `@EnableAsync`; it is not a standalone runnable Java program. `@EnableAsync` activates async method advice in the **corresponding ApplicationContext**. It does not mean Spring automatically adds a `ThreadPoolTaskExecutor` bean with the queue and pool sizes you might want.

In the default `AdviceMode.PROXY` mode:

- Callers must invoke the method through the **Spring bean proxy**, usually from another bean that injected the service.
- Internal calls like `this.sendAsync()` within the same instance bypass the proxy; the annotation may not take effect, so no executor lookup occurs on that call.
- `private` or `final` methods are not suitable interception targets for typical class-based proxies; avoid relying on proxy setups that do not support such methods.
- Do not use `@Async` directly on methods declared inside a `@Configuration` class. Place tasks on service beans.
- If the application has multiple contexts, `@EnableAsync` applies to the context where it is enabled, not automatically to all child/parent contexts.

Only once a call actually passes through the interceptor does Spring select an executor to submit the work. Calling `executor.submit(...)` directly is a different mechanism: the caller already chose the executor itself and does not participate in `@Async`'s default lookup algorithm.

## 3. Lookup Flow When @Async Does Not Specify an Executor

~~~text
Caller ---> Spring proxy ---> async interceptor
                                      |
                         Does @Async have name/qualifier?
                           | YES             | NO
                           v                  v
                 Look up Executor bean   Does AsyncConfigurer
                 by name/qualifier       provide default?
                           |                  | YES
                           v                  v
                     Use that bean       Use configured executor
                                              |
                                              | NO
                                              v
                                   Look up TaskExecutor by type
                                              |
                                  +-----------+----------+
                                  | selectable            | no
                                  v                       v
                            Use TaskExecutor      Look up "taskExecutor" bean
                                                  of type Executor
                                                      /            \
                                                    yes             no
                                                    |                |
                                                    v                v
                                                Use bean      SimpleAsyncTaskExecutor
~~~

The diagram illustrates **logical precedence**, not complete internal pseudocode. The real mechanism includes additional branches for missing beans, multiple candidates, invalid qualifiers, caching, and `BeanFactory` configuration. An explicitly specified qualifier that cannot be resolved usually results in a **bean lookup failure**; do not assume it silently falls back to the default.

## 4. Step 1: Preferring a Selectable TaskExecutor by Type

`org.springframework.core.task.TaskExecutor` is a Spring abstraction extending `java.util.concurrent.Executor`. Common implementations include `ThreadPoolTaskExecutor`, `SimpleAsyncTaskExecutor`, or `ConcurrentTaskExecutor`.

Example of a context with only one bean of type `TaskExecutor`:

~~~java
@Bean("reportPool")
ThreadPoolTaskExecutor reportPool() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(50);
    pool.setThreadNamePrefix("report-");
    return pool;
}
~~~

This is an **illustrative `@Bean` method** placed in `@Configuration`; Spring manages pool initialization and shutdown. Because `reportPool` is the sole `TaskExecutor` candidate, an unnamed `@Async` selects it by type, **even though the bean name is `reportPool`**. This configuration does not need the name `taskExecutor` to be discovered.

If multiple `TaskExecutor` beans exist, type-based lookup can become ambiguous. The `BeanFactory` mechanism may select a preferred candidate (for example via `@Primary` where applicable), but if ambiguity remains, Spring moves on to try the name `taskExecutor`.

Do not infer that `@Primary` on any arbitrary `Executor` bean will be selected like a unique `TaskExecutor`: **the first step looks for `TaskExecutor`**, and only then comes looking up an `Executor` bean by name.

## 5. Step 2: Bean Named taskExecutor as Fallback Lookup

If type lookup cannot select one, Spring searches for a bean with the **exact** name:

~~~text
taskExecutor
~~~

That bean must be compatible with `java.util.concurrent.Executor`. This name is distinct from names like `tasksExecutor`, `myTaskExecutor`, `applicationTaskExecutor`, or `asyncExecutor`.

Example when multiple `TaskExecutor` beans exist and you want to designate a stable default without adding `AsyncConfigurer`:

~~~java
@Bean("ioPool")
ThreadPoolTaskExecutor ioPool() {
    return poolWithPrefix("io-");
}

@Bean("cpuPool")
ThreadPoolTaskExecutor cpuPool() {
    return poolWithPrefix("cpu-");
}

@Bean("taskExecutor")
ThreadPoolTaskExecutor defaultAsyncPool() {
    return poolWithPrefix("default-");
}
~~~

This is an **integration snippet**: the `poolWithPrefix` helper belongs to the application and is not defined in the snippet; a complete runnable example is in section 8. When multiple `TaskExecutor` pools coexist without a type-preferred candidate, an unnamed `@Async` can pick the `taskExecutor` bean during the second lookup step.

Also note: the bean named `taskExecutor` **can be a JDK `Executor` or `ExecutorService`**, not strictly a Spring `TaskExecutor`. The interceptor has an adapter for plain executors when needed. Conversely, a bean with the right name that does not implement `Executor` is an invalid configuration that can cause a bean type error; do not expect a safe fallback on misconfigured types.

**If both a type-selectable `TaskExecutor` and another `Executor` bean named `taskExecutor` exist**, the type-lookup step takes precedence. This is a common reason why merely renaming a bean does not change the execution pool as expected.

## 6. Step 3: If Nothing Is Found, SimpleAsyncTaskExecutor

When no default executor is configured and both lookup steps fail to select one, `@EnableAsync` uses a fallback `SimpleAsyncTaskExecutor`. This is a real executor running tasks asynchronously, **not a case where Spring ignores `@Async`**.

Characteristics to remember:

- `SimpleAsyncTaskExecutor` spawns a **new thread per task** in typical usage, **not reusing threads like a thread pool**.
- Default concurrency for this type has no finite limit set by you. If concurrent requests trigger thousands of slow tasks, thread counts can spike rapidly and pressure memory, schedulers, and downstream systems.
- It offers concurrency-limit options and, on JDK 21+, a virtual-threads option; however, being used **implicitly** does not mean it has been tuned for production load.
- It is not a default `ThreadPoolTaskExecutor` with `corePoolSize=...`, `maxPoolSize=...`, or `queueCapacity=...`. You cannot use those pool properties to predict fallback behavior.
- The fallback executor is created for the interceptor infrastructure and is not equivalent to an application-managed, monitored, shared-lifecycle pool bean.

**Practical risk:** an application has two separate pools, `ioPool` and `cpuPool`, with no bean named `taskExecutor` and no explicit default. Developers assume `@Async` automatically picks a "reasonable" pool between them. Instead, it may use a local `SimpleAsyncTaskExecutor`. Therefore, declare default selection explicitly, monitor logs, and verify actual threads/pools.

## 7. Scenario Matrix to Distinguish

| Beans/Config in a Spring Framework Context | What Does Unqualified `@Async` Pick? | Reason |
| --- | --- | --- |
| Only `ThreadPoolTaskExecutor` named `reportPool` | `reportPool` | Single selectable `TaskExecutor` by type |
| Multiple `TaskExecutor`s, no preferred candidate, `Executor` named `taskExecutor` | Bean named `taskExecutor` | Type lookup ambiguous; uses fallback name |
| Multiple `TaskExecutor`s, no preferred candidate, no `taskExecutor` bean | Fallback `SimpleAsyncTaskExecutor` | Neither type nor name could resolve |
| No `TaskExecutor`, only `ExecutorService` named `backgroundPool` | Fallback `SimpleAsyncTaskExecutor` | An arbitrarily named raw `Executor` satisfies neither step 1 nor 2 |
| No `TaskExecutor`, `ExecutorService` named `taskExecutor` | Bean `taskExecutor` | Name lookup accepts `Executor` type |
| One selectable `TaskExecutor` and a raw `Executor` named `taskExecutor` | The type-selected `TaskExecutor` | Type lookup runs first |
| `AsyncConfigurer.getAsyncExecutor()` returns a concrete executor | Executor provided by `AsyncConfigurer` | Explicit default is configured |
| Method declares `@Async("reportPool")` | Bean by name/qualifier `reportPool` | Method-level override of default |

**Note on `@Primary`:** when multiple `TaskExecutor` candidates exist, `BeanFactory` can apply candidate-selection rules such as `@Primary`. Thus the claim "multiple `TaskExecutor`s **always** use the bean named `taskExecutor`" is false. Verify how beans are resolved in your specific application; prefer `AsyncConfigurer` or explicit qualifiers when multiple pools exist.

## 8. Runnable Spring Framework + Java 17 Example: Three Lookup Scenarios

The following example uses Java 17+, Maven, and Spring Framework **6.2.9**. It creates three separate `ApplicationContext` instances so beans from each scenario do not interfere with one another:

1. A single `TaskExecutor` named `analyticsPool` is selected even without the name `taskExecutor`.
2. Three `TaskExecutor`s exist, one named `taskExecutor`; Spring selects the named bean when type lookup is ambiguous.
3. No executor bean exists; Spring uses the fallback running on a thread different from the caller.

Each case invokes `Probe.threadName()` **through a Spring bean proxy** and awaits the `CompletableFuture`. We do not depend on task scheduling order.

### Project Structure

~~~text
spring-async-lookup-demo/
├── pom.xml
└── src/main/java/demo/ExecutorLookupDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-async-lookup-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ExecutorLookupDemo.java

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ExecutorLookupDemo {
    public static class Probe {
        @Async
        public CompletableFuture<String> threadName() {
            return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
        }
    }

    private static ThreadPoolTaskExecutor pool(String prefix) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix(prefix);
        return executor;
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class UniqueConfig {
        @Bean public Probe probe() { return new Probe(); }
        @Bean public ThreadPoolTaskExecutor analyticsPool() {
            return pool("unique-");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class NamedConfig {
        @Bean public Probe probe() { return new Probe(); }
        @Bean public ThreadPoolTaskExecutor firstPool() {
            return pool("first-");
        }
        @Bean public ThreadPoolTaskExecutor secondPool() {
            return pool("second-");
        }
        @Bean("taskExecutor")
        public ThreadPoolTaskExecutor preferredPool() {
            return pool("named-");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class MissingConfig {
        @Bean public Probe probe() { return new Probe(); }
    }

    private static String runIn(Class<?> configClass) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(configClass)) {
            return context.getBean(Probe.class)
                    .threadName()
                    .get(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        String callerThread = Thread.currentThread().getName();
        System.out.println("Unique TaskExecutor: " +
            runIn(UniqueConfig.class).startsWith("unique-"));
        System.out.println("Named taskExecutor: " +
            runIn(NamedConfig.class).startsWith("named-"));
        System.out.println("Fallback runs elsewhere: " +
            !runIn(MissingConfig.class).equals(callerThread));
    }
}
~~~

Run in the `spring-async-lookup-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExecutorLookupDemo
~~~

Lines of **stdout printed by the program itself**:

~~~text
Unique TaskExecutor: true
Named taskExecutor: true
Fallback runs elsewhere: true
~~~

When entering the fallback scenario, Spring **may print additional info logs** noting that no `TaskExecutor` or bean named `taskExecutor` was found; those are framework logs, not `System.out.println` lines from the example. The example was **compiled targeting Java 17 and run on OpenJDK 24**, with all three stdout lines verified. The values `core=1`, `max=2`, `queue=4` are for testing only, not production defaults.

Why the results are reliable:

- Each context is isolated so the algorithm only sees that scenario's beans.
- `@EnableAsync` enables proxying in all three contexts; `Probe` is created as a bean and retrieved from Spring, not called via `new Probe().threadName()` in the caller.
- `@Async` specifies no name, so all three exercise the default lookup algorithm.
- `CompletableFuture.completedFuture(...)` is created **inside the worker**; the proxy returns a real future representing async execution to the caller. `get(5, SECONDS)` provides a bounded wait to check the result.
- The `unique-` and `named-` prefixes clearly distinguish the selected executors. The no-executor case is verified by checking that the thread differs from the caller, without hard-coding the fallback executor's prefix.
- `try`-with-resources closes `AnnotationConfigApplicationContext`, so `ThreadPoolTaskExecutor` beans declared with `@Bean` have their lifecycle managed by Spring.

## 9. When to Switch From Default Lookup to Explicit Selection?

This lesson's algorithm applies only when an `@Async` call through a proxy **specifies no name** and has no default from `AsyncConfigurer`. If you want a method to always use the I/O pool, write `@Async("ioExecutor")` and ensure a compatible bean exists. When multiple unqualified methods share the same default, implement `AsyncConfigurer.getAsyncExecutor()` returning a Spring-managed executor bean.

To distinguish at the call site: `@Async` uses type/name/fallback lookup; `@Async("billingExecutor")` selects that bean or qualifier; `CompletableFuture.supplyAsync(...)` in plain Java code uses the passed-in executor or JDK default, without participating in Spring lookup.

Do not create a new pool per request. For executors created manually outside `@Bean`, the application must manage initialize/shutdown; for Spring beans, let the container handle lifecycle. The operational goal is picking a bounded, observable pool rather than relying on a hard-to-control fallback.

## 10. Special Case: Spring Boot May Have Created an Executor Earlier

**Plain Spring Framework** and **Spring Boot auto-configuration** are two separate layers of behavior.

In **Spring Boot 3.5** as an example, when no matching application-declared `Executor` bean exists, Boot typically auto-configures an `AsyncTaskExecutor` bean:

- Usually a `ThreadPoolTaskExecutor` using Boot-supplied configuration.
- When running on Java 21+ with virtual threads enabled, Boot may use a `SimpleAsyncTaskExecutor` configured for virtual threads.
- The auto-configured bean is typically named `applicationTaskExecutor` and can be picked up by `@Async` via type lookup, **without needing to rename it to `taskExecutor`**.
- When an application-supplied `Executor` bean is present, auto-configuration may back off; consult your **exact Spring Boot version and actual configuration** to determine which executors remain active.
- Spring MVC, WebFlux, GraphQL, and other integrations may expect a bean named `applicationTaskExecutor` of a specific type; that name has its own significance and is not identical to Spring Framework's `taskExecutor` fallback.

Therefore, do not write "without any config, `@Async` is guaranteed to use `SimpleAsyncTaskExecutor`" for **every Spring Boot app**. That statement holds for plain Framework lookup when no default executor or eligible bean truly exists, whereas Boot may create an executor before that algorithm runs.

Also distinguish: `@EnableAsync` activates annotation-based async; `spring.task.execution.*` configures the Boot-managed executor when the corresponding auto-configuration applies. If properties are present while the active executor bean is custom or a fallback, those properties may not take effect as expected.

## 11. Common Ambiguous or Misconfigured Cases

### 11.1. Multiple TaskExecutors With None Named taskExecutor

~~~text
@Bean("emailPool")     ThreadPoolTaskExecutor
@Bean("reportPool")    ThreadPoolTaskExecutor
No @Primary or AsyncConfigurer
No bean named taskExecutor
~~~

This describes a scenario, not complete Java code. If type lookup cannot resolve, Spring does not pick `emailPool` or `reportPool` at random; it looks up `taskExecutor` by name and may then fall back to `SimpleAsyncTaskExecutor`. **Fix:** use explicit names/qualifiers, select a default via `AsyncConfigurer`, or designate a resolvable default candidate.

### 11.2. A Bean Named taskExecutor Exists Alongside Another Type-Eligible Candidate

~~~text
TaskExecutor bean: paymentPool (unique candidate by type)
Executor bean: taskExecutor (does not implement TaskExecutor)
~~~

If `paymentPool` is the sole `TaskExecutor` candidate, it is chosen **before** the bean named `taskExecutor`. Renaming the second bean will not change the precedence rule by itself. **Fix:** specify an explicit name on the method or configure `AsyncConfigurer`.

### 11.3. Missing @EnableAsync or Self-Invocation

If `@Async` is not enabled or the call bypasses the proxy, the method may run **synchronously on the caller thread**. Do not diagnose this as "Spring picked the wrong executor"; at that point the interceptor has not even entered the call.

### 11.4. Creating an ExecutorService and Assuming Spring Will Auto-Select It

An `ExecutorService` bean named `myExecutor` is only a JDK `Executor`, not necessarily a Spring `TaskExecutor`. With no `TaskExecutor` beans and the bean not named `taskExecutor`, the Framework's default algorithm will not select `myExecutor`. **Fix:** name it `taskExecutor`, use `AsyncConfigurer`, or write `@Async("myExecutor")`.

### 11.5. Assuming the Application Has Only One Spring ApplicationContext

In web applications with parent/child contexts, a bean living in another context or an annotation enabled in only one context can yield unexpected lookup results. Verify the exact context containing the interceptor/proxied bean and which executor beans are visible to it.

## 12. How to Confirm the Actual Executor at Runtime

Reading configuration is only the first step; testing threads and metrics proves which selection was applied:

1. **Assign distinct thread name prefixes** to each `ThreadPoolTaskExecutor`: `email-`, `billing-`, `report-`. Inside the task, log `Thread.currentThread().getName()` with an operation ID.
2. **Retrieve beans from the Spring context**, invoke `@Async` from outside the declaring bean, and observe outcomes; never instantiate with `new` in tests.
3. **Inspect types and names:** list `TaskExecutor` candidates, `Executor` beans named `taskExecutor`, `AsyncConfigurer`, and method/class qualifiers. When using Spring Boot, also inspect `applicationTaskExecutor` and auto-configuration.
4. **Enable appropriate logging** to spot fallback warnings; some versions log messages like "No task executor bean found for async processing" when no bean matches.
5. **Check pool metrics:** active workers, core/max, queue size, rejected tasks, and thread-name prefixes. If `@Async` genuinely runs on a specific pool, metrics and thread names must agree.
6. **Test overload:** with `ThreadPoolTaskExecutor`, task submission can be rejected upon saturation; with the unbounded default concurrency of `SimpleAsyncTaskExecutor` fallback, load profiles look very different.

Never rely **solely** on seeing `main` as the thread name in logs to conclude a proxy is missing: an executor might use `CallerRunsPolicy` to run tasks on the caller thread under overload. Combine config checks, proxy checks, thread names, metrics, and a non-saturated test to distinguish them.

## 13. Picking the Right Executor Is Not Enough for Business Guarantees

Once you know which executor Spring submits `@Async` tasks to, separate contracts still need design:

- **Exceptions:** methods returning `CompletableFuture`/`Future` allow callers to observe completion and failure. With `@Async void`, exceptions do not return to the caller's stack; Spring uses `AsyncUncaughtExceptionHandler` (defaulting to logging).
- **Rejection:** a full queue or shut-down executor can fail task submission immediately; the business method has not executed on a worker. Handle backpressure, error reporting, and bounded retries where appropriate.
- **Transactions:** with imperative transactions, the transaction is bound to the worker thread; an open HTTP request transaction does not carry over to the async thread. Define transaction boundaries on the worker if DB operations occur.
- **Thread safety:** a singleton bean can be invoked concurrently by multiple requests; choosing a pool does not protect shared mutable state.
- **Execution context:** `ThreadLocal`, MDC, and security/request context are not guaranteed to propagate into workers automatically. Use proper propagation mechanisms, clean up context reliably, and pass immutable commands where possible.
- **Ordering and delivery:** thread pools do not guarantee FIFO execution across tasks or exactly-once execution across instances. `@Async` does not make work survive crashes; durability requires a job store/queue/idempotency.
- **Lifecycle:** Spring-managed `ThreadPoolTaskExecutor` beans have shutdown/configuration hooks; the local fallback is not equivalent to an observable application pool bean.

If your workload mixes blocking I/O, CPU-bound work, and tasks with different risk profiles, use **explicitly chosen** executors per group rather than relying on hard-to-govern default names.

## 14. Unambiguous Testing

A useful integration test suite for this topic should cover:

1. **Single TaskExecutor:** register one bean with a custom prefix, call unqualified `@Async`; assert the thread name has that prefix.
2. **Multiple TaskExecutors + taskExecutor:** register multiple type candidates and one bean named `taskExecutor`; assert the fallback name prefix.
3. **No candidates:** context with only `@EnableAsync` + service; assert the task runs on a thread other than the caller, noting any fallback log if present.
4. **Explicit `@Async` qualifier:** declare `@Async("ioExecutor")` alongside a different default; assert the IO executor is chosen.
5. **Self-invocation:** call via `this` to demonstrate proxy bypass in default proxy mode; keep separate from real async tests.
6. **Isolated ApplicationContexts:** avoid leaking beans across scenarios, and keep Boot auto-configuration from altering plain Framework tests.
7. **Failures and overload:** when a bounded pool saturates, assert the rejection policy and caller handling; when a task throws, assert the Future/handler receives the expected error.

These tests verify what matters—that **the right executor is actually selected**—not merely that a bean exists. Section 8's example demonstrates the three central scenarios without hard-coding a specific fallback thread name.

## 15. Safe @Async Configuration Checklist

- I know which context enables `@EnableAsync` and that calls pass through a Spring proxy.
- I know whether the method has an `@Async("...")` qualifier or an `AsyncConfigurer`.
- I have inventoried all `TaskExecutor` beans and confirmed whether type lookup is unique/unambiguously prioritized.
- I have checked for a bean named exactly `taskExecutor`, whose type must be `Executor`.
- I do not assume Boot's `applicationTaskExecutor` is identical to Framework's `taskExecutor` fallback.
- I do not rely on the `SimpleAsyncTaskExecutor` fallback for unbounded production traffic.
- I intentionally configure core/max/queue/rejection, shutdown, and metrics when using a thread pool.
- I distinguish a submitted task from a successfully completed task.
- I control exceptions, transactions, context propagation, and shared mutable state for tasks.
- I verify via an integration test and thread-prefix logs rather than reading annotations alone.

**Conclusion:** When `@Async` is enabled with no explicit executor configuration, the Spring Framework prioritizes **`TaskExecutor` by type**, then **`Executor` named `taskExecutor`**, and finally falls back to **`SimpleAsyncTaskExecutor`**. In Spring Boot, auto-configuration may pre-create an executor, so always inspect the actual runtime context before drawing conclusions.

## Official References

- [Spring Framework – EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): executor lookup algorithm, fallback, proxies, and AsyncConfigurer.
- [Spring Framework – AsyncExecutionAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionAspectSupport.html): type/name lookup and per-method executor selection.
- [Spring Framework – Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html): method/class qualifiers, `Future` and `CompletableFuture` return types.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): enabling `@Async`, qualifiers, and exception management.
- [Spring Framework – SimpleAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html): thread creation, concurrency limits, and lifecycle.
- [Spring Boot 3.5 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, auto-configuration, and `@EnableAsync` interaction.
