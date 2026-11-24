# Selecting a Default Executor With `AsyncConfigurer`

**Module:** Spring Framework - concurrency  
**Knowledge Group:** Enabling `@Async`  
**Focus:** Intentionally choosing the executor used for `@Async` methods that do not specify a pool name, distinguishing default configuration from `@Async("beanName")`, managing executor lifecycle, and handling exceptions properly.

## 1. Problem: Which Pool Does `@Async` Run On?

In a Spring application, a method marked with `@Async` can be handed off by Spring to an executor to run at another time. Simply adding the annotation, however, does not answer critical operational questions:

- How many threads are allowed to run?
- Which queue does the work enter, and is the queue bounded?
- How are tasks rejected under overload?
- Can one service running slow I/O exhaust workers needed by other services?
- When multiple executor beans exist, which one will a method **without an executor name** choose?
- Where are errors in `void`-returning methods handled?

`AsyncConfigurer` is Spring's extension point for supplying the **default executor** for the `@Async` infrastructure and, if needed, an **exception handler for `@Async void` methods**.

```text
Call from bean A -> Spring proxy of bean B
                         |
                         | Does @Async specify an executor name?
                         |
              +----------+-----------+
              |                      |
         @Async("ioExecutor")     @Async
              |                      |
              v                      v
       Bean "ioExecutor"     AsyncConfigurer.getAsyncExecutor()
              |                      |
              +----------+-----------+
                         |
                   Selected Executor
                         |
                 Worker / queue / rejection
                         |
                     Completion
```

Distinguish **choosing an executor** from **enabling the @Async mechanism**:

- `@EnableAsync` enables `@Async` discovery/interception in the corresponding **application context**.
- `AsyncConfigurer` supplies the default choice when an `@Async` call does **not** specify another executor.
- `@Async("beanName")` routes that specific call to the executor bean with the matching name/qualifier.
- The actual executor determines threads, queuing, admission limits, and rejection behavior. `AsyncConfigurer` does **not** create a thread pool on its own merely because the interface is implemented.

## 2. What Does the `AsyncConfigurer` Interface Provide?

In Spring Framework 6.2, the interface in `org.springframework.scheduling.annotation` has two **default** methods:

```java
package org.springframework.scheduling.annotation;

// Signature sketch, not the framework's full source code.
public interface AsyncConfigurer {
    default java.util.concurrent.Executor getAsyncExecutor() {
        return null;
    }

    default org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return null;
    }
}
```

This is a **sketch to understand the API**, not an exact copy of Spring source code; use the interface provided by the library. Two extension points:

1. **`getAsyncExecutor()`** returns the `java.util.concurrent.Executor` Spring uses as the default for `@Async` without a specified executor. It can return a `ThreadPoolTaskExecutor`, a JDK `ExecutorService`, or another valid implementation. Returning `null` causes Spring to apply its normal default executor lookup.
2. **`getAsyncUncaughtExceptionHandler()`** returns the `AsyncUncaughtExceptionHandler` used when a `void`-returning `@Async` method throws an exception and the caller has no `Future` to observe it. Returning `null` uses Spring's default handler.

`AsyncConfigurer` does **not** replace `@EnableAsync`, does **not** control `@Scheduled`, does not create a durable queue, and does not guarantee the calling thread's context/transaction is propagated to workers.

Because Spring uses proxies to execute `@Async`, methods must be called **through a Spring-managed proxy** in the default `AdviceMode.PROXY` mode. Internal calls like `this.doAsync()` bypass the proxy, so the annotation may be ignored.

## 3. What Does AsyncConfigurer Change Compared to Default Lookup?

If `AsyncConfigurer.getAsyncExecutor()` returns a concrete executor, the infrastructure uses it for `@Async` calls **without a specified name**. If no suitable default is configured, the Spring Framework searches for a unique `TaskExecutor` bean by type, then looks for an `Executor` bean named exactly `taskExecutor`, and finally falls back to `SimpleAsyncTaskExecutor`. Spring Boot may auto-configure an executor under its own conditions; inspect the actual context.

| Case | Executor Used |
| --- | --- |
| Unnamed `@Async` and AsyncConfigurer returns pool X | Pool X |
| `@Async("ioExecutor")` | Bean/qualifier `ioExecutor`, even if the default is X |
| AsyncConfigurer returns no executor | Type/name lookup then Framework fallback if needed |

This is the boundary of **choosing a default with AsyncConfigurer**: do not treat arbitrary bean names or auto-configuration as proof of which pool is used. When multiple candidates exist, test in practice using thread prefixes/bean wiring; type/name lookup rules and ambiguous cases are covered separately in the lesson on the executor resolution algorithm.

## 4. Minimal Configuration Pattern and Common Lifecycle Pitfalls

Pattern from Spring documentation:

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {

    @Override
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("async-");
        executor.initialize();
        return executor;
    }
}
```

This is an **illustrative class snippet**; the corresponding imports are required:

```java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
```

Key point to remember: a `ThreadPoolTaskExecutor` constructed directly in the method above **does not automatically become a fully managed Spring bean** merely because the method sits inside `@Configuration`. Calling `initialize()` is required in manual creation examples; you must also arrange shutdown/lifecycle when the application closes.

**Preferred approach with Spring-managed lifecycle:** add `@Bean` to `getAsyncExecutor()` or define a separate executor bean and return that bean. When `ThreadPoolTaskExecutor` is a container-managed bean, Spring calls initialization and destruction lifecycle hooks automatically; **no manual `initialize()` call is needed**.

Notably, `AsyncConfigurer` may be initialized **early** during context bootstrapping. If the configuration needs another Spring dependency, consider `ObjectProvider<T>` or lazy injection and avoid eagerly initializing an entire graph of proxied/post-processed beans. Do not inject a complex business service into the configurer just to compute thread counts.

## 5. Runnable Spring Boot Example: Default, Qualified Pool, and `void` Errors

The complete example below uses **Java 17+**, **Spring Boot 3.5.7** (Spring Framework 6.2.x), and Maven. It creates:

- A default executor named `configuredAsyncExecutor`, with thread names starting with `default-`.
- Another executor named `ioExecutor`, with thread names starting with `io-`.
- A service using `@Async` **without a name**, and a method using `@Async("ioExecutor")`.
- A failing `CompletableFuture`-returning method observed from the future.
- A failing `@Async void` method routed to `AsyncUncaughtExceptionHandler`.

Both pools have bounded queues. The main program **intentionally awaits Futures to verify behavior**; do not use this pattern as an immediate-response HTTP API.

### 5.1. Project Structure

```text
async-configurer-demo/
├── pom.xml
└── src/main/java/com/example/asyncconfig/
    ├── AsyncConfigurerDemoApplication.java
    ├── AsyncConfiguration.java
    └── AsyncJobService.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>async-configurer-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

`spring-boot-starter-aop` provides proxy/AOP support and the required Spring foundation components; no web server is needed to demonstrate `@Async`.

### 5.3. `src/main/java/com/example/asyncconfig/AsyncConfiguration.java`

```java
package com.example.asyncconfig;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    // Only for the demo program to verify the void handler once.
    public static final CompletableFuture<String> VOID_FAILURE =
            new CompletableFuture<>();

    @Override
    @Bean("configuredAsyncExecutor")
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("default-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(3);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("io-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, parameters) ->
                VOID_FAILURE.complete(
                        method.getName() + ":"
                        + exception.getClass().getSimpleName());
    }
}
```

**Explanation:**

- `@EnableAsync` activates proxy advice for `@Async`.
- `getAsyncExecutor()` returns the default `Executor`. `@Bean("configuredAsyncExecutor")` makes the actual executor a Spring-managed bean, including proper `initialize` and `destroy`.
- `ioExecutor()` creates a second bean. It does **not** automatically replace the default choice, because the configurer already returns the `default-` pool.
- `VOID_FAILURE` is a **single-use error-observation bridge for the demo program**, not a production error-tracking system. Real applications use loggers/metrics/tracing with full context.
- `AbortPolicy` rejects submissions when the pool and queue can accept no more tasks. `ThreadPoolTaskExecutor` expresses rejection per Spring's contract (`TaskRejectedException`).
- The core/max/queue settings are illustrative only and must be tuned to real CPU, I/O, RAM, downstream limits, and SLOs.

### 5.4. `src/main/java/com/example/asyncconfig/AsyncJobService.java`

```java
package com.example.asyncconfig;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncJobService {

    @Async
    public CompletableFuture<String> defaultJob() {
        String thread = Thread.currentThread().getName();
        String pool = thread.startsWith("default-")
                ? "default" : "unexpected";
        return CompletableFuture.completedFuture(pool);
    }

    @Async("ioExecutor")
    public CompletableFuture<String> ioJob() {
        String thread = Thread.currentThread().getName();
        String pool = thread.startsWith("io-")
                ? "io" : "unexpected";
        return CompletableFuture.completedFuture(pool);
    }

    @Async
    public CompletableFuture<String> failedFutureJob() {
        throw new IllegalStateException("demo failure");
    }

    @Async
    public void failedVoidJob() {
        throw new IllegalArgumentException("demo void failure");
    }
}
```

`defaultJob()` has no qualifier, so it uses the pool returned by `AsyncConfigurer`. `ioJob()` explicitly specifies `"ioExecutor"`, so it is routed to the dedicated pool. Both methods are invoked from **another bean** through the Spring proxy in the main program.

A method with a `CompletableFuture<T>` signature can return `CompletableFuture.completedFuture(value)` inside its implementation to supply the worker-computed result; the caller receives the future provided by the proxy. Exceptions from `failedFutureJob()` cause the caller's future to complete with error; `AsyncUncaughtExceptionHandler` is **not** where that future error is handled.

### 5.5. `src/main/java/com/example/asyncconfig/AsyncConfigurerDemoApplication.java`

```java
package com.example.asyncconfig;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class AsyncConfigurerDemoApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app =
                new SpringApplication(AsyncConfigurerDemoApplication.class);

        // Run in CLI mode without starting an HTTP server.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            AsyncJobService jobs = context.getBean(AsyncJobService.class);

            System.out.println("default=" +
                    jobs.defaultJob().get(5, TimeUnit.SECONDS));

            System.out.println("qualified=" +
                    jobs.ioJob().get(5, TimeUnit.SECONDS));

            try {
                jobs.failedFutureJob().get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("futureError=" +
                        ex.getCause().getClass().getSimpleName());
            }

            jobs.failedVoidJob();
            System.out.println("voidError=" +
                    AsyncConfiguration.VOID_FAILURE.get(
                            5, TimeUnit.SECONDS));
        }
    }
}
```

`try-with-resources` closes the Spring context once the demo finishes; bean-managed executors follow Spring lifecycle management. `Future.get(timeout, unit)` here **intentionally waits** for deterministic output and error inspection, and does not represent a reasonable choice for an HTTP controller with tight deadlines.

### 5.6. Running and Observing

Prerequisites: JDK 17+ and Maven installed. In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Expected `System.out` lines when the program finishes normally:**

```text
default=default
qualified=io
futureError=IllegalStateException
voidError=failedVoidJob:IllegalArgumentException
```

The application disables the Spring banner and root logger output in the example to focus on the results. Even if build/runtime tools or the environment print extra lines of their own, only these four lines are actively printed by `main`. Actual worker completion order may vary, but `main` reads each outcome via a future, so the order of these four `System.out` lines is fixed.

**Why is this proof of proper executor selection?**

1. `defaultJob()` runs on a thread prefixed with `default-`; not on the `ioExecutor` bean even though two pools exist in the context.
2. `ioJob()` runs on a thread prefixed with `io-`; the method qualifier overrides the default selection.
3. `failedFutureJob()` places the exception into the future; `Future.get()` throws `ExecutionException` whose `getCause()` is `IllegalStateException`.
4. `failedVoidJob()` has no future to inspect; `AsyncConfigurer`'s handler receives the exception and completes `VOID_FAILURE` for `main` to check.

Never build production logic around **thread names**. Prefixes are purely for demonstration and debugging; in real systems, track the chosen executor via beans, task metrics, and tracing.

## 6. When Does `@Async("...")` Override the Default Executor?

The default from `AsyncConfigurer` applies to **`@Async` calls without an executor qualifier**. With a qualifier, Spring routes to the designated bean.

```java
@Service
public class ExportService {

    @Async
    public CompletableFuture<String> smallExport() {
        return CompletableFuture.completedFuture("small");
    }

    @Async("largeExportExecutor")
    public CompletableFuture<String> largeExport() {
        return CompletableFuture.completedFuture("large");
    }
}
```

This is an **illustrative class snippet** in a Spring application: it requires imports for `@Service`, `@Async`, `CompletableFuture`, and an existing `"largeExportExecutor"` bean. If the bean does not exist or is incompatible with the required executor, invocation can fail; Spring should not silently pick a random pool and hide configuration errors.

You can place `@Async("defaultPool")` at the class level and specify another executor on a method per annotation rules; the method's specific selection generally takes precedence over the class level. Use clear bean/qualifier names when a service handles multiple categories of tasks.

**Note:** `getAsyncExecutor()` does not intercept manually written `CompletableFuture.supplyAsync(...)` or `ExecutorService.submit(...)` calls in your code. Direct JDK calls use the executor passed to them or the JDK's own default, without consulting Spring's `AsyncConfigurer`.

## 7. Catching Exceptions Properly: `void` and `Future` Differ

Spring requires different error-handling points depending on the method signature:

| Return Type of `@Async` Method | What Does the Caller See? | Error Handling Approach |
| --- | --- | --- |
| `void` | No result/future to wait on | `AsyncUncaughtExceptionHandler`, logs/metrics/alerts |
| `Future<T>` | `Future` representing the task | `get()` throws `ExecutionException` if task fails |
| `CompletableFuture<T>` | Can `get`, `join`, `whenComplete`, `handle` | Use completion stages and handle exceptional completion |
| Arbitrary values like `String` | Not a supported return type for `@Async` | Change to `void`/`Future`/`CompletableFuture` per contract |

Example handler for `void` methods in a real application:

```java
@Override
public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
    return (error, method, arguments) -> {
        log.error("Async void method {} failed",
                method.getName(), error);
        failedTaskCounter.increment();
    };
}
```

This snippet is **not a standalone program**; `log` and `failedTaskCounter` are dependencies supplied by the application. Method arguments can contain sensitive data; never log all `arguments` unconditionally without a protection policy.

With `CompletableFuture`:

```java
CompletableFuture<Report> future = reportService.createReport(id);

future.whenComplete((report, error) -> {
    if (error != null) {
        recordFailure(id, error);
    } else {
        recordSuccess(id, report);
    }
});
```

This is an illustrative snippet assuming `reportService`, `id`, type `Report`, and two result-recording functions. `whenComplete` is for observation; exceptions thrown by the callback itself also have exceptional completion semantics to monitor. Avoid leaving futures from important work unobserved.

**Do not expect a worker exception to be thrown directly back to a synchronous caller.** The exception occurs after the `@Async` call has been handed to the executor; by contrast, **rejection errors at submission time** can happen immediately when the caller invokes the method.

## 8. Lifecycle and Early Initialization of `AsyncConfigurer`

### Two Ways to Supply an Executor and Their Different Responsibilities

**Manual creation inside `getAsyncExecutor()` (no `@Bean`):**

```java
@Override
public Executor getAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(10);
    executor.initialize();
    return executor;
}
```

You must clarify who owns and closes the executor. Because the object is not fully managed by the container, do not automatically assume Spring invokes destroy. If the application creates multiple uncontrolled instances, threads can leak.

**Returning a Spring bean:**

```java
@Override
@Bean("configuredAsyncExecutor")
public Executor getAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(10);
    return executor;
}
```

When the method is actually registered by Spring as a `@Bean`, bean lifecycle manages initialize/destroy and no manual `initialize()` call is needed. This is also the pattern used by the complete runnable example above.

### What If the Executor Bean Is Defined Elsewhere?

Some projects place executors in another configuration module, or use beans with complex decorators/monitoring. `AsyncConfigurer` is initialized early; avoid hard dependencies that cause bootstrap cycles. Illustrative configuration:

```java
@Configuration
@EnableAsync
class AsyncSetup implements AsyncConfigurer {
    private final ObjectProvider<Executor> executorProvider;

    AsyncSetup(
            @Qualifier("sharedAsyncExecutor")
            ObjectProvider<Executor> executorProvider) {
        this.executorProvider = executorProvider;
    }

    @Override
    public Executor getAsyncExecutor() {
        return executorProvider.getObject();
    }
}
```

This is an **illustrative snippet dependent on the Spring context**, requiring imports for `java.util.concurrent.Executor`, `@Configuration`, `@EnableAsync`, `AsyncConfigurer`, `ObjectProvider`, `@Qualifier`, and an existing `"sharedAsyncExecutor"` bean. `ObjectProvider` defers bean retrieval until needed, helping avoid eager initialization of proxied dependencies. Do not create multiple scattered `AsyncConfigurer` classes expecting each to choose a different pool; the default is a context-wide setting, while individual methods can use qualifiers.

### Shutdown Considerations

- `ThreadPoolTaskExecutor` is a lifecycle-aware Spring bean; the application must close the context properly.
- Tasks running or queued at shutdown need an explicit policy: continue/wait/cancel and stop deadlines; exact behavior depends on Spring version, executor settings, and container lifecycle.
- Do not shut down the pool at the end of every request if the pool is a shared bean.
- Having `AsyncConfigurer` itself does not persist tasks to disk/DB. If the JVM dies, in-memory queues can be lost even when bean lifecycles are well managed.
- A separate Spring child context may not automatically inherit the parent's `@EnableAsync` the way you expect; documentation states `@EnableAsync` applies within the **local application context**.

## 9. How Large Should the Pool Be and How Should Rejection Work?

`getAsyncExecutor()` returns an `Executor`; actual capacity configuration lives on that executor. For `ThreadPoolTaskExecutor`, the three core parameters are:

| Parameter | Meaning | Common Mistake |
| --- | --- | --- |
| `corePoolSize` | Baseline worker count normally maintained per pool mechanics | Setting too low while hoping `maxPoolSize` is always used |
| `maxPoolSize` | Upper bound on workers created when load and queue allow | Thinking `max` equals how many tasks run immediately |
| `queueCapacity` | Queued tasks waiting, excluding currently running tasks | Setting too large so requests expire past deadlines while sitting in the queue |

With the underlying `ThreadPoolExecutor` model, once core workers are busy, tasks are usually **queued first**; only when the queue accepts no more does the pool try expanding up to `maxPoolSize`. If both pool and queue are full, tasks are rejected.

Starting examples for two kinds of workloads:

- **CPU-bound:** workers roughly matching available CPU budget after accounting for other JVM load; fixed or nearly fixed pool; bounded queue.
- **Blocking I/O:** may need more workers than CPU cores because many threads wait on network/DB, yet still constrained by connection pools, rate limits, timeouts, and RAM.
- **Critical business tasks:** consider durable jobs via DB/queue/broker instead of only pushing into an in-JVM executor.

In an application with two pools, set a **total budget** based on system resources. Routing default `@Async` to pool A and `@Async("ioExecutor")` to pool B does not multiply CPU cores or DB connections.

### Rejection Under Overload

`ThreadPoolTaskExecutor` follows Spring's `TaskRejectedException` rejection convention. With `AbortPolicy`, task submission can fail immediately when the pool lacks capacity. If a controller wants to report "accepted for processing," distinguish successful submission from rejection:

```java
try {
    reportService.submitAsync(id);
    // Only respond accepted if the contract genuinely allows
    // accepting tasks into memory; durability must be designed separately.
} catch (TaskRejectedException ex) {
    // Map to an intentional overload error, such as HTTP 503.
}
```

This is an **illustrative snippet**, with application-defined `reportService`, `id`, `TaskRejectedException`, and HTTP response handling. If the requirement is **never lose jobs across restarts**, write to a durable DB/broker before returning `202`, rather than treating `executor.execute(...)` as durable confirmation.

JDK's `CallerRunsPolicy` can run the task on the **submitting thread** when the pool rejects, blocking the HTTP thread. Therefore, if you need fail-fast behavior, select an intentional rejection policy. `@Async` does not guarantee execution on a separate thread in every case if you choose a delegate or policy with inline-execution behavior.

## 10. Common Mistakes When Selecting a Default Executor

| Mistake | Symptom | How to Check/Fix |
| --- | --- | --- |
| Forgetting `@EnableAsync` | `@Async` calls still run on the caller thread | Enable it in the right application context |
| Calling `this.doAsync()` inside the same bean | Bypasses proxy, does not offload to executor | Call through another Spring bean, redesign boundaries |
| Two executors exist and unclear which is chosen | Unqualified method runs on an unexpected pool | Use `AsyncConfigurer` or `@Async("beanName")`, verify actual beans |
| Thinking `getAsyncExecutor()` configures all async APIs | `CompletableFuture.supplyAsync` or `@Scheduled` still use other resources | Pass executors explicitly to JDK APIs; configure schedulers separately |
| Using executor without `@Bean` and without calling `initialize()` | Spring pool not properly initialized | Initialize and manage lifecycle manually, or make it a Spring bean |
| Initializing `AsyncConfigurer` with complex/eagerly autowired dependencies | Beans/proxies not ready, bootstrap errors | Use lazy `ObjectProvider`, keep configuration cleanly separated |
| Thinking `@Bean` returning `Executor` loses `ThreadPoolTaskExecutor` lifecycle | Worrying about needing extra `initialize` calls | The actual bean is still `ThreadPoolTaskExecutor`; Spring manages lifecycle |
| `@Async void` throws exception with no tracking handler | Caller never receives error | Configure `AsyncUncaughtExceptionHandler`, logs/metrics |
| `CompletableFuture` fails but is ignored | Background failure goes unobserved | `whenComplete`/`handle`/`get`, job state tracking |
| Creating a new pool inside each method/request | Thread leaks, no app-wide bounds | Shared executor bean, shutdown tied to context |
| Unbounded queue, huge `maxPoolSize` | Growing backlog, max threads rarely reached, OOM | Bounded queue, proper sizing, and rejection policy |
| Testing only thread names without behavioral tests | Misses overload/exception/timeout bugs | Test executor type, concurrent task count, rejection, and shutdown |
| Arbitrarily copying transaction/request context via ThreadLocal | Reads uncommitted data, leaks security context | Worker opens its own transaction; pass IDs/data explicitly and clean up properly |
| Putting CPU-heavy tasks on I/O pool, or vice versa | Starvation, unstable p99 | Partition pools by resource profile, measure in practice |

## 11. Testing Configuration in Real Projects

**Minimum functional tests:**

1. Enable `@EnableAsync` on a component-scanned config class.
2. Implement `AsyncConfigurer` returning a configured executor with a distinct `threadNamePrefix`.
3. Call a public `@Async` method **through another bean** and verify it uses the pool returned by the configurer.
4. Define a second executor bean; use `@Async("otherExecutor")` and verify the qualifier picks the right pool.
5. Trigger the `void` failure branch and verify `AsyncUncaughtExceptionHandler` receives the exception.
6. Trigger the `CompletableFuture` failure branch and verify exceptional completion.
7. Fill the queue using `CountDownLatch`, verifying rejection/response rather than using `Thread.sleep` to guess races.
8. Close the context to verify no leaked threads remain and in-flight tasks are handled properly.

**Operational testing:** under realistic load, measure active threads, queue depth, queue wait, task execution time, reject count, p95/p99 latency, CPU throttling, JDBC/HTTP connections, and startup/shutdown. Getting the API configuration right does not mean capacity matches the workload.

**Scenario needing dedicated measurement:** even with `@Async` enabled, a controller might receive a `CompletableFuture` yet still block the request if it calls `.get()`/`.join()` immediately. If the goal is freeing Servlet threads **while keeping an HTTP response waiting for the result**, use Spring MVC's async request support appropriately. If you want to return `202 Accepted` for long background processing, you need separate job/status/durability APIs.

## 12. Self-Check Questions

**1.** There are two `ThreadPoolTaskExecutor` beans `"cpuExecutor"` and `"ioExecutor"`, and you want all unqualified `@Async` methods to default to `"cpuExecutor"`. What do you choose?  
**A:** Implement `AsyncConfigurer.getAsyncExecutor()` returning the `cpuExecutor` bean (or configure the application with an explicit default rule). Methods needing the I/O pool use `@Async("ioExecutor")`.

**2.** Must `getAsyncExecutor()` return `ThreadPoolTaskExecutor`?  
**A:** No, the return type is `java.util.concurrent.Executor`; the implementation can be a JDK executor or another suitable type, provided it meets contracts/operational needs.

**3.** Why does adding `@Bean` to `getAsyncExecutor()` matter?  
**A:** The returned executor becomes a Spring bean; initialization/destruction lifecycle hooks are managed by the container if it is a lifecycle-aware type like `ThreadPoolTaskExecutor`.

**4.** Does an `@Async("ioExecutor")` method use the executor returned from `AsyncConfigurer`?  
**A:** Usually not. The name/qualifier specified on `@Async` requests the matching bean and overrides the default choice for that call.

**5.** If `@Async void` throws `IllegalArgumentException`, can the caller catch it with `try/catch` around the call?  
**A:** Not in the normal way when the task runs later on a worker; `AsyncUncaughtExceptionHandler` receives the error. Exceptions at **task submission time**, such as rejection, are a different case.

**6.** `@Async CompletableFuture<String>` fails; does the `void` handler catch it?  
**A:** No. The caller must observe the failed future via `get()`, `whenComplete`, or an equivalent mechanism.

**7.** `this.generate()` has `@Async` yet still runs synchronously; what is wrong?  
**A:** Self-invocation bypasses the proxy in default `AdviceMode.PROXY`.

**8.** Why might `maxPoolSize=32` only show four running workers when the queue is not full?  
**A:** `ThreadPoolExecutor` typically queues tasks beyond core size before spawning workers past core. Understand `corePoolSize`, `queueCapacity`, and deadlines.

**9.** Should `AsyncConfigurer` create a `new ThreadPoolTaskExecutor()` on every incoming request?  
**A:** No. The executor is shared across the context with a single configuration and explicit lifecycle; requests only submit tasks to the executor.

**10.** Does `getAsyncExecutor()` guarantee jobs are processed after a JVM restart?  
**A:** No. This selects the in-JVM execution pool. Durability requires persistence/queues/brokers and recovery.

## 13. Key Takeaways

`AsyncConfigurer` lets you **transparently select the default executor for `@Async`** and provides a handler for **exceptions in `void` methods**. Configuration affects calls passing through Spring's async advice in the corresponding context; `@Async("beanName")` can target a dedicated pool.

- **Enable:** `@EnableAsync`.
- **Choose default:** implement `AsyncConfigurer.getAsyncExecutor()`.
- **Choose specific:** `@Async("ioExecutor")`.
- **Handle errors:** `getAsyncUncaughtExceptionHandler()` for `void`; `Future`/`CompletableFuture` observed by callers or job orchestration.
- **Manage lifecycle:** prefer Spring-bean executors, bounded queues, and context-driven shutdown.
- **Verify:** call through Spring proxies, measure threads/queues/rejections, test under load, and specify explicit contracts when jobs must outlive HTTP requests.

**Official Documentation:**

- [Spring Framework 6.2 — `@EnableAsync` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): executor lookup rules, `AsyncConfigurer` examples, lifecycle, proxies.
- [Spring Framework 6.2 — `AsyncConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html): two configuration methods and early-init notes.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): abstractions, `@Async`, executors, exception handling.
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): pool configuration and lifecycle.
- [Java SE 17 — `Executor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): base JDK contract.