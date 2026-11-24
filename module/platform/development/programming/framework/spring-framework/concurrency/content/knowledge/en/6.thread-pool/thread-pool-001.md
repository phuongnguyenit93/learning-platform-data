# Declaring ThreadPoolTaskExecutor as a Container-Managed Bean

> **Topic:** Spring Framework – Concurrency / Thread Pool.  
> **Primary Goal:** create a `ThreadPoolTaskExecutor` as a Spring bean, explicitly configure the pool size and queue, inject the right bean where it is used, and delegate **resource initialization and destruction management to the Spring container**. A production-ready executor must also have appropriate overload handling, shutdown, and observability policies.

## 1. Learning Outcomes

After completing this lesson, you will be able to:

1. Explain the difference between `new ThreadPoolTaskExecutor()` as a plain Java object and an object declared with `@Bean`/registered in the `ApplicationContext`.
2. Write Java configuration using `@Configuration` and `@Bean("...")` for `ThreadPoolTaskExecutor` without manually calling `initialize()` or `shutdown()` when the container owns the bean.
3. Understand the impact of `corePoolSize`, `maxPoolSize`, `queueCapacity`, `keepAliveSeconds`, `threadNamePrefix`, and `RejectedExecutionHandler`.
4. Use constructor injection and `@Qualifier` when multiple executors exist; specify an executor via `@Async("beanName")` when needed.
5. Run a Spring Context + Java 17 example that verifies execution threads, bean identity, and shutdown using synchronization signals instead of `Thread.sleep()`.
6. Design deliberate overload and application shutdown behavior; avoid thread leaks, lost tasks, and accidental request slowdowns.

## 2. What Is ThreadPoolTaskExecutor?

`org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` is a Spring class that wraps `java.util.concurrent.ThreadPoolExecutor` and provides the `TaskExecutor`/`AsyncTaskExecutor` interface. It lets you configure familiar thread pool properties via JavaBean-style setters, for example:

- Core and maximum thread counts.
- Queue capacity.
- Idle thread keep-alive time.
- Thread name prefix.
- How to handle tasks when the executor cannot accept them.
- How to respond when the Spring context closes.

The application submits tasks via `execute(Runnable)` or an appropriate `Future`-returning API; the Spring executor uses workers/a queue to run tasks as configured. Calling `execute` is **not** a request to create a new thread for every task.

### When Should You Use It?

Use `ThreadPoolTaskExecutor` when you need to bound and manage task execution within **a single JVM**, such as image processing, sending emails, computing reports, or integration tasks that can run asynchronously. To guarantee tasks survive a crash/restart, you need a durable storage mechanism such as a message queue/job store; an in-memory thread pool does not provide that capability.

### What Does a Container-Managed Bean Mean?

Basic lifecycle diagram:

~~~text
@Configuration / @Bean
        |
        v
Spring creates the ThreadPoolTaskExecutor object
        |
        v
Apply configuration (core/max/queue/name/policy...)
        |
        v
Spring calls afterPropertiesSet() -> initialize()
        |
        v
Executor is ready to accept tasks via DI / @Async
        |
        v
ApplicationContext begins closing
        |
        v
Spring coordinates lifecycle and calls destroy() -> shutdown()
~~~

`ThreadPoolTaskExecutor` extends `ExecutorConfigurationSupport` and implements `InitializingBean`, `DisposableBean`, and Spring lifecycle protocols. When it is a container-owned bean, calling `afterPropertiesSet()` to create the underlying `ExecutorService` happens during bean initialization; when the bean is destroyed, the container invokes the corresponding destruction callback. In real applications, `ApplicationContext` must be closed in an orderly fashion for these callbacks to run.

**Key point:** inside a `@Bean` factory method, you **instantiate the object, set its properties, and `return` it**. Do not call `executor.initialize()` inside `@Bean`, because the container automatically performs this step during the bean lifecycle; manual invocation can cause duplicate initialization and make executor management harder to control. Likewise, never manually call `shutdown()` from a service that uses the shared bean.

## 3. Clean and Concise @Bean Configuration Pattern

In a project with `spring-context` or an appropriate Spring Boot starter:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerPoolConfig {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("report-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(15);
        return executor;
    }
}
~~~

This is a **Spring configuration class**, not a standalone application. When the container scans or imports `WorkerPoolConfig`:

1. The bean has the exact name `reportExecutor` and concrete type `ThreadPoolTaskExecutor`.
2. Spring initializes the pool during the bean's initialization phase; callers do not need to call `initialize()` manually.
3. Other components can inject it by name/type to share the default singleton bean instance.
4. When the context closes, Spring coordinates shutdown. With wait-for-tasks-to-complete enabled, the pool processes previously accepted work before closing within the specified timeout constraints.

`@Configuration(proxyBeanMethods = false)` is valid for configuration methods that rely on DI parameters. If one `@Bean` method needs another bean, receive it via a **method parameter** rather than calling another factory method in the same configuration class and assuming you always get the managed bean.

### Property-by-Property Breakdown

| Configuration | Meaning | Practical Notes |
| --- | --- | --- |
| `setCorePoolSize(2)` | Baseline number of workers the pool aims to maintain under load | Does not mean 2 threads are eagerly pre-created at startup |
| `setMaxPoolSize(4)` | Upper bound on pool workers | Can only grow beyond core when the queue policy allows, typically after the queue is full |
| `setQueueCapacity(16)` | Maximum number of queued tasks when workers are busy | A bounded queue prevents unbounded growth, though rejections can occur at peak load |
| `setKeepAliveSeconds(30)` | Idle retention time for workers above core | Does not expire core threads by default; see `setAllowCoreThreadTimeOut(...)` |
| `setThreadNamePrefix(...)` | Sets the worker thread name prefix | Aids debugging in thread dumps/logs; does not provide isolation or synchronization |
| `setRejectedExecutionHandler(...)` | Determines behavior when the pool cannot accept a task | `AbortPolicy` throws an exception; `CallerRunsPolicy` may execute the task on the caller thread |
| `setWaitForTasksToCompleteOnShutdown(true)` | On shutdown, prefers completing running and queued tasks rather than interrupting/discarding them via the default path | Can prolong shutdown time; requires bounding and coordinating dependent resources |
| `setAwaitTerminationSeconds(15)` | Instructs the container to wait up to 15 seconds for executor termination | The timeout **does not guarantee** all tasks will finish within 15 seconds |

These are **example values**, not universal tuning parameters for every system. Choose values based on CPU/I/O workload, connection limits, memory, task submission/consumption rates, latency goals, and resource exhaustion handling.

### Default Values to Avoid Misinterpreting

According to the Spring 6.2 Javadoc, `ThreadPoolTaskExecutor` defaults to `corePoolSize = 1`, a very large `maxPoolSize`, and a very large `queueCapacity`. Because the queue can keep accepting work, this configuration in practice behaves almost like a single worker with a long queue, even though `maxPoolSize` looks unbounded. **Do not assume the default pool automatically scales threads with incoming requests.**

- `queueCapacity > 0`: Spring typically uses a `LinkedBlockingQueue` with the configured capacity.
- `queueCapacity = 0`: uses a direct handoff mechanism like `SynchronousQueue`; the pool can spawn extra workers up to `maxPoolSize` if needed.
- Large queue: reduces rejections during small bursts but increases wait times and the risk of retaining many tasks/payloads in RAM.
- Very small queue: reacts faster to overload but requires explicit rejection/backpressure design.

## 4. Runnable Java 17+ Example with Spring Context

This example demonstrates the **complete bean lifecycle**, from creating the `ApplicationContext`, injecting `TaskExecutor` into a service, running a task on another worker thread, to closing the context. It does not require Spring Boot or an HTTP server.

### 4.1. Project Structure

~~~text
managed-pool-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ManagedPoolDemo.java
~~~

File **`pom.xml`** (Java 17, Spring Framework 6.2.16):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>managed-pool-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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

File **`src/main/java/demo/ManagedPoolDemo.java`**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ManagedPoolDemo {

    @Configuration(proxyBeanMethods = false)
    static class PoolConfig {

        @Bean("reportExecutor")
        ThreadPoolTaskExecutor reportExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(4);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("report-");
            pool.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            pool.setWaitForTasksToCompleteOnShutdown(true);
            pool.setAwaitTerminationSeconds(5);
            return pool;  // Spring calls initialize() and destroy().
        }

        @Bean
        ReportService reportService(
                @Qualifier("reportExecutor") TaskExecutor taskExecutor) {
            return new ReportService(taskExecutor);
        }
    }

    static final class ReportService {
        private final TaskExecutor executor;

        ReportService(TaskExecutor executor) {
            this.executor = executor;
        }

        void runOnce(AtomicReference<Thread> used,
                     CountDownLatch completed) {
            executor.execute(() -> {
                try {
                    used.set(Thread.currentThread());
                } finally {
                    completed.countDown();
                }
            });
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread caller = Thread.currentThread();
        ThreadPoolTaskExecutor pool;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PoolConfig.class)) {

            pool = context.getBean(
                    "reportExecutor", ThreadPoolTaskExecutor.class);
            ReportService service = context.getBean(ReportService.class);

            System.out.println("same bean = " +
                    (pool == context.getBean("reportExecutor")));

            AtomicReference<Thread> used = new AtomicReference<>();
            CountDownLatch completed = new CountDownLatch(1);
            service.runOnce(used, completed);

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task timed out");
            }

            System.out.println("different thread = " +
                    (used.get() != caller));
            System.out.println("worker named = " +
                    used.get().getName().startsWith("report-"));
        } // context.close() invokes the bean's shutdown lifecycle.

        System.out.println("pool shutdown = " +
                pool.getThreadPoolExecutor().isShutdown());
    }
}
~~~

### 4.2. Compiling and Running

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ManagedPoolDemo
~~~

**Program stdout** on a successful run (ignoring any Maven-specific messages):

~~~text
same bean = true
different thread = true
worker named = true
pool shutdown = true
~~~

Explanation of each result:

- Two calls to `getBean("reportExecutor")` return the same instance because `@Bean` definitions are singletons in the context by default.
- The task is submitted to the active pool and executed by a worker with prefix `report-`, so comparing against the caller thread yields `true` for `different thread`. Under this light load, `AbortPolicy` has no reason to reject the task.
- `CountDownLatch` ensures the task has written `AtomicReference<Thread>` before the main thread reads it; no `sleep()` is used.
- `try-with-resources` closes `AnnotationConfigApplicationContext` right after the `try` block. `ThreadPoolTaskExecutor` was initialized and destroyed by Spring according to its lifecycle, so `isShutdown()` returns `true`.

**Why didn't the example call `pool.initialize()` and `pool.shutdown()`?** Because the container owns the lifecycle. Calling `initialize()` inside `@Bean` is unnecessary; calling `shutdown()` from a service can cause other consumers of the shared bean to suddenly receive `TaskRejectedException`.

### When Not Running Inside a Spring Context

This is a **different** situation:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.initialize();
try {
    executor.execute(() -> System.out.println("work"));
} finally {
    executor.shutdown();
}
~~~

This snippet is a **manual illustration**, assuming the code runs inside a method; it has no `main` method itself. When you instantiate the object outside a bean factory, **you** must initialize, shut down, and await termination if needed. This explains the value of turning the executor into a Spring bean: the container centralizes lifecycle, DI, and configuration, reducing the risk of forgetting to clean up resources.

## 5. Injecting and Using the Right Bean

### Constructor Injection with @Qualifier

When a system has multiple executors, inject the explicitly named bean:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class InvoiceExportService {
    private final TaskExecutor reportExecutor;

    public InvoiceExportService(
            @Qualifier("reportExecutor") TaskExecutor reportExecutor) {
        this.reportExecutor = reportExecutor;
    }

    public void enqueue(long invoiceId) {
        reportExecutor.execute(() -> export(invoiceId));
    }

    private void export(long invoiceId) {
        // Execute export business logic; handle retries/errors at the appropriate layer.
    }
}
~~~

This is a **service snippet for a component-scanned Spring project**, not a standalone Java SE file. The `@Qualifier("reportExecutor")` name must match the bean name or an active qualifier. If only one `TaskExecutor` bean exists, you can inject by type; when multiple beans of the same type exist, specify a qualifier or designate a primary bean to avoid ambiguity.

### Why Choose TaskExecutor in Services?

Most services only need the `execute(...)` method, so they can depend on `TaskExecutor` rather than a concrete class. The Spring configuration holds pool size, queue, and shutdown details; business logic only knows it hands tasks to the provided executor. If a service needs `submit(...)` APIs, use an appropriate interface like `AsyncTaskExecutor` or a deliberate concrete dependency.

### Interaction with @Async

`@Async` is a Spring annotation mechanism backed by proxies/interceptors. If you want a method to be dispatched through a specific bean, enable `@EnableAsync` in configuration and specify the bean name:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncFeatureConfig {
}

@Service
class InvoicePreviewService {
    @Async("reportExecutor")
    public CompletableFuture<String> generatePreview(long id) {
        String result = "preview-" + id;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

These are **two illustrative classes in a Spring application**; if placed in the same file, they must follow Java's naming/public class rules. An `@Async("reportExecutor")` method uses the bean named `reportExecutor` when invoked **through the Spring proxy**. With the default proxy mode, calling `this.generatePreview(...)` from within the same class bypasses the interceptor and executes as a normal synchronous Java call.

`@Async` does not automatically preserve persistence or transactions across threads; on a different thread, the caller's transaction context/`ThreadLocal` is not propagated by default. If you need error handling, returning `CompletableFuture`/`Future` gives the caller better visibility into failures than `void`.

## 6. Inside the Thread Pool: Core, Queue, Max, and Rejection

`ThreadPoolTaskExecutor` uses the pool management rules of `ThreadPoolExecutor`. With `corePoolSize = 2`, `maxPoolSize = 4`, and `queueCapacity = 3`, imagine a scenario where tasks run long enough to keep occupying workers:

| Consecutive tasks submitted while all are busy | Idealized behavior |
| --- | --- |
| Tasks 1–2 | Uses up to 2 core workers |
| Tasks 3–5 | Can wait in the 3 queue slots |
| Tasks 6–7 | Pool can create additional workers up to a max of 4 |
| Task 8 | Workers and queue are both full: triggers the rejection policy |

This table is a **simulation assuming tasks do not finish during submission**, not a fixed execution schedule forecast. If a worker finishes early, newly submitted tasks may be accepted differently.

- `AbortPolicy` (underlying executor default): rejects when unable to accept, typically surfacing as `TaskRejectedException` through Spring's `TaskExecutor`.
- `CallerRunsPolicy`: if the pool is not shut down, a task rejected by the pool runs directly on **the thread calling `execute`**. This provides backpressure but can unexpectedly slow down requests.
- `DiscardPolicy` or `DiscardOldestPolicy`: risks losing tasks; should not be used for mandatory business work without a compensating/monitoring mechanism.
- When the pool is shutting down or shut down, submissions may be rejected; with `CallerRunsPolicy`, the JDK does not run rejected tasks once the executor has shut down.

**Do not equate "handed to the pool" with "guaranteed to run on another thread"** if `CallerRunsPolicy` is enabled. Do not claim "guaranteed execution" just because `execute` did not throw an exception when a handler can silently discard tasks.

### Rejection Handling Example

~~~java
import org.springframework.core.task.TaskRejectedException;

public void submitJob(Runnable job) {
    try {
        reportExecutor.execute(job);
    } catch (TaskRejectedException ex) {
        // Offload to a durable queue, perform bounded retries,
        // or report overload to the client depending on business needs.
        throw ex;
    }
}
~~~

This is an **illustrative method pattern**, assuming `reportExecutor` has been injected. Avoid unbounded retries directly on the request thread, as that adds load precisely when the pool is already saturated. For critical jobs, design idempotent messages, retries, and durable state storage rather than relying solely on an in-memory queue.

## 7. Bean Lifecycle and Safe Application Shutdown

### 7.1. Automatic Initialization

`ThreadPoolTaskExecutor` inherits the `InitializingBean.afterPropertiesSet()` mechanism, which calls `initialize()`. Spring invokes this callback after applying bean properties, creating the underlying pool for task submission.

Therefore, inside `@Bean`:

~~~java
@Bean("imageExecutor")
ThreadPoolTaskExecutor imageExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(50);
    return executor; // Do not call initialize() manually here.
}
~~~

If you need the pool in another component, inject that bean. **Do not** write `new ThreadPoolTaskExecutor()` inside every request or service just to "use it immediately"; this creates multiple pools without a unified lifecycle, wastes threads, and easily leads to forgotten shutdowns.

### 7.2. Automatic Shutdown

`ThreadPoolTaskExecutor` implements `DisposableBean.destroy()`, inherited from `ExecutorConfigurationSupport`. When the context closes properly, Spring invokes the destruction callback to shut down the underlying executor. This is why you do not need an extra `@PreDestroy` method just to call `shutdown()` on the same bean.

However, **container-managed shutdown does not mean every task has completed**. You must distinguish between:

- Stopping acceptance of new tasks.
- How currently running tasks are handled.
- How tasks sitting in the queue are handled.
- Whether to wait for tasks to finish, and for how long at most.
- Whether other beans (database clients, HTTP clients, etc.) stay alive long enough for running tasks to use them.

### 7.3. Two Critical Shutdown Properties

In Spring Framework 6.2:

`setWaitForTasksToCompleteOnShutdown(true)` instructs the executor during shutdown to let already accepted tasks complete without proactively interrupting them on the normal shutdown path, including tasks still in the queue. This can lengthen shutdown duration if there is a backlog or a hung task.

`setAwaitTerminationSeconds(15)` instructs the shutdown phase to wait up to 15 seconds for the executor to terminate before Spring proceeds to destroy remaining beans. It **does not forcibly finish** every task after 15 seconds in a way that guarantees completion; if it times out, tasks may still remain or require application-level shutdown orchestration.

Combining both properties should be based on actual job runtimes. If a job can take several minutes, a 15-second value is just a short wait policy, not a guarantee that the job finishes before the database pool closes.

### 7.4. Specific Note on Lifecycle Changes in Spring 6.1/6.2

Recent Spring versions coordinate executor shutdown with `ContextClosedEvent` and `SmartLifecycle`. Properties such as `acceptTasksAfterContextClose` and, on `ThreadPoolTaskExecutor`, `strictEarlyShutdown` affect when new tasks are rejected during context closure.

Do not memorize a simplistic rule like "calling `context.close` immediately stops every task." Read the Javadoc for your **running version** and test your application's actual shutdown order. Do not start new background tasks inside destruction callbacks assuming the pool will still accept work, unless the lifecycle design explicitly allows and verifies it.

### 7.5. Should You Add destroyMethod="shutdown" Manually?

For a Spring-managed `ThreadPoolTaskExecutor`, **no**, because the class already provides the standard destruction callback. Typical configuration examples simply use `@Bean("...")` and return the executor. Calling `shutdown()` in multiple places can cause remaining work to be rejected; even worse, a pool consumer should never be given the responsibility of closing a shared pool.

If you want to opt a special bean out of container shutdown, that is a separate design decision requiring manual lifecycle management; it does not apply to the standard managed-bean pattern in this lesson.

## 8. Naming and Separating Executors by Workload Type

An application may have multiple pools:

~~~java
@Configuration(proxyBeanMethods = false)
class MultiplePoolsConfig {

    @Bean("cpuExecutor")
    ThreadPoolTaskExecutor cpuExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("cpu-");
        return pool;
    }

    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(8);
        pool.setMaxPoolSize(16);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("io-");
        return pool;
    }
}
~~~

**Illustrative configuration snippet**, not default tuning pairs. CPU-bound thread counts usually need to align with available CPUs; long-waiting I/O tasks may need different concurrency levels while accounting for DB/HTTP connection limits, memory, and task submission rates. If load isolation is unnecessary, one clearly configured pool is sometimes simpler than multiple pools.

When injecting:

~~~java
public SomeService(
        @Qualifier("cpuExecutor") TaskExecutor cpuExecutor,
        @Qualifier("ioExecutor") TaskExecutor ioExecutor) {
    this.cpuExecutor = cpuExecutor;
    this.ioExecutor = ioExecutor;
}
~~~

This is only a **constructor snippet**: in a real class, you must declare the corresponding two `TaskExecutor` fields. Distinct bean names and `@Qualifier` prevent type-based injection from suddenly becoming ambiguous when a second executor is added.

## 9. Spring Boot Configuration: Watch Out for the Default Bean

Spring Boot auto-configures executors depending on the version and present beans. For example, in **Spring Boot 3.5**, when no custom `Executor` is present, Boot can auto-create an `AsyncTaskExecutor` for various integrations, typically a `ThreadPoolTaskExecutor` when using platform threads.

**When you declare a custom `Executor` bean**, auto-configuration may back off, and features such as `@Async`, Spring MVC async handling, or WebFlux may select a different executor by **bean name and type**. These rules depend on the Boot version:

- `@Async("reportExecutor")`: explicitly selects the `reportExecutor` bean for that specific method.
- For certain web async integrations, the bean name `applicationTaskExecutor` and implementing `AsyncTaskExecutor` carry special meaning.
- With `@EnableAsync` configuration, Spring Framework has a mechanism to pick the default executor and can use `AsyncConfigurer`; do not assume any arbitrarily named bean will automatically be used by all tasks.
- Distinguish between an executor for `@Async` and a scheduler for `@Scheduled`. A `ThreadPoolTaskExecutor` does not automatically become a `TaskScheduler`.

**Practical rule:** if your project uses Spring Boot, read the exact "Task Execution and Scheduling" section for your **deployed Boot version**, inspect the actual list of registered beans, and intentionally assign names/qualifiers. Do not duplicate pools just to add another executor without understanding auto-configuration effects.

## 10. TaskDecorator, Context, and Worker Errors

`ThreadPoolTaskExecutor#setTaskDecorator(...)` lets you wrap tasks before execution, useful for logging/tracing or controlled context propagation.

**Illustrative** example, placed in the factory method before `return executor`:

~~~java
executor.setTaskDecorator(original -> () -> {
    long started = System.nanoTime();
    try {
        original.run();
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        System.out.println("Task runtime nanos = " + elapsedNanos);
    }
});
~~~

`TaskDecorator` applies to the `Runnable` prepared by the executor; for `submit(...)` paths wrapped in `FutureTask`, exception handling inside the decorator may not behave as expected. To observe task exceptions, use `Future.get()`/`CompletableFuture`, an appropriate exception handler, or executor-specific hooks.

**Do not blindly copy every `ThreadLocal` from the request to the worker.** Spring transactions are typically thread-bound; security context, MDC tracing, and request attributes may require dedicated propagation mechanisms. If you capture/set context in a decorator, you must restore/clear it in `finally` so reused workers do not leak data from a previous task into the next one.

In particular, using `CallerRunsPolicy` can cause tasks to execute on the caller thread at times, changing observed latency and context. Choose a rejection handler aligned with your application's operational and security requirements.

## 11. Monitoring and Verifying a Running Bean

To inspect the live pool at runtime, retrieve the bean from the context:

~~~java
ThreadPoolTaskExecutor pool =
        context.getBean("reportExecutor", ThreadPoolTaskExecutor.class);

int currentPoolSize = pool.getPoolSize();
int activeThreads = pool.getActiveCount();
int queuedTasks = pool.getThreadPoolExecutor().getQueue().size();
~~~

This is a **snippet inside code with an initialized `context`**. These numbers represent point-in-time observations that change as tasks start/finish; they are not transactionally consistent snapshots. You can export them to Micrometer/Actuator or a suitable monitoring system, but avoid logging every single task under heavy load.

### Metrics to Watch

| Metric | What to Observe |
| --- | --- |
| Active threads | Whether it stays pinned near max continuously |
| Queue depth | Whether the queue grows relentlessly and how long backlogs take to drain |
| Rejected submissions | Spikes in rejections and impact on callers |
| Task duration / error rate | Whether tasks are slow due to external I/O or CPU, and whether errors are routed properly |
| Caller latency | Sharp spikes caused by `CallerRunsPolicy` or submission waits |
| Shutdown duration | Whether the container stops before critical tasks finish |

Good throughput or latency cannot be inferred from `corePoolSize` alone; test empirically with a workload matching production resource characteristics.

### Meaningful Lifecycle Testing

1. Start the context and retrieve `reportExecutor`; verify you get the expected bean name/type.
2. Submit a task and use `CountDownLatch` or `Future` to wait for completion—never use `Thread.sleep`.
3. Compare `Thread.currentThread()` with the caller if off-thread execution is part of the configuration contract.
4. Close the context; check the underlying `ThreadPoolExecutor.isShutdown()` and, if needed, `awaitTermination(...)`.
5. For overload tests, deliberately hold workers with a latch, fill the queue, then submit another task to verify the rejection policy. Do not rely on scheduler luck.
6. Test exceptions, cancellation, shutdown duration, and resource cleanup according to business needs.

A test passing under light load **does not prove** the pool will never reject tasks or always run off the caller thread when `CallerRunsPolicy` is configured.

## 12. Common Mistakes When Declaring Beans

**Mistake 1: creating a pool with `new` on every request.**  
Consequence: unbounded thread growth and difficult shutdown management. Fix: define a shared singleton bean for the specific workload and inject it into services.

**Mistake 2: calling `initialize()` manually inside the `@Bean` method.**  
Consequence: the container also invokes the initialization callback. Fix: configure properties and `return` the executor, letting Spring manage the lifecycle.

**Mistake 3: forgetting to define when the pool stops.**  
Consequence: when creating pools manually, omitting shutdown keeps threads/processes alive; for a bean, the context must close properly. Fix: use container-managed beans and design appropriate shutdown timeouts.

**Mistake 4: assuming `maxPoolSize=100` means 100 tasks run concurrently immediately.**  
Consequence: with a very large queue, the pool usually enqueues tasks before scaling beyond core. Fix: understand the worker/queue priority algorithm and size queue capacity deliberately.

**Mistake 5: leaving the queue unbounded to "never fail."**  
Consequence: rising latency, large payloads held in RAM, and out-of-memory risk. Fix: set reasonable bounds, control submission rate, and handle rejections.

**Mistake 6: configuring `CallerRunsPolicy` while assuming tasks always run in the background.**  
Consequence: the request thread may execute the task itself and slow down unexpectedly; execution context changes. Fix: pick a handler matching your goal and monitor saturation.

**Mistake 7: injecting solely by type when multiple executors exist.**  
Consequence: ambiguity or using the wrong pool. Fix: give beans meaningful names and use `@Qualifier` or `@Async("...")`.

**Mistake 8: declaring the bean and assuming `@Async` is automatically active.**  
Consequence: the annotation may be ignored without `@EnableAsync`/equivalent support, or self-invocation bypasses the proxy. Fix: enable async support and invoke through the Spring proxy.

**Mistake 9: assuming `@Bean` makes mutable fields in a service thread-safe.**  
Consequence: lost updates or corrupted reads when multiple tasks share the same singleton. Fix: design immutable state or proper synchronization; the pool manages threads, not business invariants.

**Mistake 10: thinking a successful shutdown means all critical work was durably saved.**  
Consequence: crashes or timeouts can still lose in-memory tasks. Fix: use a job store/message broker when durability, retries, and idempotency are required.

**Mistake 11: enabling `waitForTasksToCompleteOnShutdown` with an insufficient timeout and ignoring resource dependencies.**  
Consequence: tasks keep running after the beans they depend on have already closed. Fix: evaluate worst-case duration, test real graceful shutdown, and adjust ordering/timeouts.

**Mistake 12: adding `@PreDestroy` in a consumer to shut down a shared bean.**  
Consequence: one consumer can cause other consumers' tasks to be rejected and tangle destruction order. Fix: let the executor bean own its lifecycle via the container.

## 13. Applied Exercises

### Exercise 1 — Fill in the Missing Configuration

The following snippet lacks the configuration needed to distinguish a pool used for report generation tasks:

~~~java
@Bean("reportExecutor")
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(20);
    return pool;
}
~~~

**Suggested answer:** add `setThreadNamePrefix("report-")`; choose an appropriate `RejectedExecutionHandler`. For tasks that must finish at shutdown, consider `setWaitForTasksToCompleteOnShutdown(...)` and `setAwaitTerminationSeconds(...)`. There is no need to call `initialize()` in the factory method.

### Exercise 2 — Why Are Only Two Workers Running?

A pool has `corePoolSize=2`, `maxPoolSize=20`, and `queueCapacity=Integer.MAX_VALUE`. When hundreds of short tasks are submitted consecutively, why are only a few workers busy?

**Answer:** after the core workers, the pool prioritizes placing tasks into the queue; a massive queue almost never fills up, so it rarely gets a chance to spawn workers beyond core. To increase concurrency under load, you must tune queue capacity and pool sizing together, not just raise `maxPoolSize`.

### Exercise 3 — Which Bean Does @Async Use?

An application has `reportExecutor` and `notificationExecutor`. A method is annotated with `@Async("notificationExecutor")`.

**Answer:** Spring selects the bean by the qualifier/name `notificationExecutor` when async interception is active. If invoked directly via `this` in proxy mode, you cannot assume the call will be dispatched through the executor.

### Exercise 4 — Does Shutdown Guarantee Clearing the Entire Queue?

An executor has 1,000 queued tasks, `setWaitForTasksToCompleteOnShutdown(true)`, and `setAwaitTerminationSeconds(5)`. Can you guarantee all tasks finish within 5 seconds?

**Answer:** no. Configuring a maximum 5-second wait does not turn a long workload into short tasks or guarantee the queue drains before the deadline. You must control backlog volume, timeouts, and explicitly define how unfinished jobs are handled.

### Exercise 5 — Analyze the Broken Code

~~~java
@Service
class WrongReportService {
    void start() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.execute(() -> System.out.println("report"));
    }
}
~~~

**Answer:** the manually created pool never called `initialize()`, so it has no underlying executor; calling `execute` lacks an initialized pool and will fail. If you fix it by calling `initialize()` manually without `shutdown()`, you introduce a thread leak risk. The right approach in a Spring application: declare a `@Bean` and constructor-inject the lifecycle-managed pool.

## 14. Checklist for Reviewing a ThreadPoolTaskExecutor Bean

- [ ] The executor is created once via `@Bean`/appropriate bean registration and managed by the Spring context.
- [ ] A clear `@Bean` name is set, and services use constructor injection with `@Qualifier` when multiple pools exist.
- [ ] Neither `initialize()` in the factory method nor `shutdown()` in a consumer is called manually.
- [ ] `corePoolSize`/`maxPoolSize`/`queueCapacity` are chosen for the workload, with memory bounds and overload behavior.
- [ ] `RejectedExecutionHandler` and the error/fallback queue path on rejection are well understood.
- [ ] Thread name prefix aids observability without using thread names as the sole proof of correctness.
- [ ] With `@Async`: `@EnableAsync` is enabled, calls go through the proxy, and the executor is specified when needed.
- [ ] Graceful shutdown, wait timeouts, resource closing order, and handling of incomplete tasks are designed.
- [ ] Queue depth, active threads, rejections, and latency are measured; saturation behavior is tested.
- [ ] If tasks must survive crashes, durable storage outside the executor is used.

## 15. Core Takeaways

**Practical recipe:** `@Configuration` + `@Bean("executorName")` + `new ThreadPoolTaskExecutor()` + required setters + `return executor`. Spring manages initialize/destroy; services receive the bean via dependency injection.

Pool size, queue, and rejection form **one unified policy**, not three independent numbers. For production safety, also account for context closure, task results, transactions/dependent resources, and required durability mechanisms. When using `@Async`, identify the exact selected executor and ensure calls pass through the proxy.

## Official References

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 — `ExecutorConfigurationSupport` Javadoc (initialize, destroy, shutdown, await): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Boot 3.5 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Spring Framework — Bean Definition and Lifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
