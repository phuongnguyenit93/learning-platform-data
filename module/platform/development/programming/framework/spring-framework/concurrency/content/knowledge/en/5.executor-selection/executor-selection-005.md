# ConcurrentTaskExecutor: Adapting an Existing Executor in Spring Framework

## Goal and Use Case

When an application already has a Java executor, such as an `ExecutorService` created by a library, infrastructure configuration, or another component, you may want to use **that same executor** in Spring APIs that require a `TaskExecutor` or `AsyncTaskExecutor`. `org.springframework.scheduling.concurrent.ConcurrentTaskExecutor` is an **adapter** for that situation.

After this lesson, you will be able to:

1. Explain the relationship between `java.util.concurrent.Executor`, `ExecutorService`, Spring's `TaskExecutor`, `AsyncTaskExecutor`, and `ConcurrentTaskExecutor`.
2. Wrap an existing JDK executor with `new ConcurrentTaskExecutor(existingExecutor)` and understand where tasks run.
3. Use the adapter as a bean with `@Async("springExecutor")`, or call `execute`/`submit` directly.
4. Identify which party owns the thread pool, queue, rejection policy, shutdown, and monitoring.
5. Decide when to use `ConcurrentTaskExecutor`, `TaskExecutorAdapter`, `ThreadPoolTaskExecutor`, or `ConcurrentTaskScheduler`.

**Key idea:** `ConcurrentTaskExecutor` **does not create an additional pool** when you pass in an existing executor. It provides a Spring-compatible API surface and **delegates execution** down to the underlying executor. Actual runtime behavior is still governed by the underlying executor.

## 1. The Problem the Adapter Solves

Suppose a system has already configured:

```java
java.util.concurrent.ExecutorService existing =
    java.util.concurrent.Executors.newFixedThreadPool(2);
```

`existing` is a JDK executor. A Spring component may want an `org.springframework.core.task.AsyncTaskExecutor` to submit work and receive a `Future` uniformly. We can adapt it:

```java
import org.springframework.scheduling.concurrent.ConcurrentTaskExecutor;

ConcurrentTaskExecutor springExecutor = new ConcurrentTaskExecutor(existing);
```

These two lines only illustrate the wiring, not a standalone program: imports, lifecycle management for `existing`, and closing the pool when no longer used are still needed.

Actual flow:

```text
Caller or Spring component
        |
        | execute(task) / submit(callable)
        v
ConcurrentTaskExecutor                 <-- adapter using Spring's API
        |
        | delegates to the same Executor provided
        v
Existing java.util.concurrent.Executor <-- decides scheduling,
        |                                  threads, queue, rejection
        v
Thread executing the work
        |
        +----> finishes, Future completes or fails
```

**Do not confuse “adapting an interface” with “changing execution policy”.** The adapter does not change the underlying executor's worker count, queue, priority, cancellation, timeout, or shutdown behavior. Nor does it guarantee that every task runs on a different thread from the caller: a JDK `Executor` is permitted to execute synchronously.

## 2. Distinguishing Related Interfaces

| Type | Core contract | Key takeaway |
| --- | --- | --- |
| JDK `Executor` | `void execute(Runnable task)` | Only requests execution; may run inline, queue, or reject. |
| JDK `ExecutorService` | Extends `Executor` with `submit`, `Future`, `shutdown`, lifecycle management | May be a thread pool, though not always a pool you configured yourself. |
| Spring `TaskExecutor` | Extends `Executor`'s concept with `execute(Runnable)` | Common entry point for Spring to accept an executor; Spring error conventions include `TaskRejectedException`. |
| Spring `AsyncTaskExecutor` | Extends `TaskExecutor`, adding submission of `Callable` tasks and returning `Future`/`CompletableFuture` | Helps Spring components handle asynchronous results through a common interface. |
| Spring `ConcurrentTaskExecutor` | Adapter taking a JDK `Executor` while implementing Spring's execution interfaces | Still uses the passed-in executor; supports `execute`, `submit`, and configuring `TaskDecorator`. |
| Spring `SchedulingTaskExecutor` | Exposes certain scheduling-related traits to task submitters | **Not** a `TaskScheduler`; does not provide APIs to schedule by time or cron. |

In Spring Framework 6.2, `ConcurrentTaskExecutor` implements both `AsyncTaskExecutor` and `SchedulingTaskExecutor`; it also supports adapting `ExecutorService` and detecting Jakarta `ManagedExecutorService` in appropriate environments.

### How Does `execute` Differ from `submit`?

`execute(Runnable)` submits a job with no return value. The method can return control to the caller before the task finishes if the executor runs asynchronously. If the executor rejects at submission time, the caller receives the error upon submission.

`submit(Callable<T>)` returns a `Future<T>` so the caller can retrieve the value, wait, or observe errors:

```java
Future<Integer> future = springExecutor.submit(() -> 21 * 2);
Integer value = future.get(); // may block the caller until done
```

This is a usage snippet inside a method that already has the adapter and declares/handles `get()` exceptions. In a complete example later, we use `CompletableFuture` with `@Async`.

When the delegate is an `ExecutorService`, the adapter can leverage the delegate's `submit` capability. If it is only a basic `Executor`, Spring can use a `FutureTask`-style wrapper and submit it via `execute`. **Having a `Future` does not prove tasks run in parallel**: inspect the delegate's policy.

## 3. When to Choose ConcurrentTaskExecutor?

| Context | Suitable choice | Reason |
| --- | --- | --- |
| Already have an `Executor`/`ExecutorService` to reuse via Spring API | `ConcurrentTaskExecutor(existingExecutor)` | Wraps the already configured/coordinated executor without creating a new pool. |
| Need only a minimal adapter from JDK `Executor` to Spring `AsyncTaskExecutor` | `TaskExecutorAdapter` in `org.springframework.core.task.support` | Lighter adapter, useful when `ConcurrentTaskExecutor`'s extra integration features are unneeded. |
| Want Spring to configure and manage a thread pool via bean properties | `ThreadPoolTaskExecutor` | Provides `corePoolSize`, `maxPoolSize`, `queueCapacity`, lifecycle control, and suitable monitoring. |
| Already have a `ScheduledExecutorService` and want the `TaskScheduler` scheduling API | `ConcurrentTaskScheduler` | This is the adapter for scheduling; **do not** use `ConcurrentTaskExecutor` instead. |
| Running in a Jakarta EE server with a container-managed executor | `DefaultManagedTaskExecutor` or an adapter to the appropriate managed executor | Uses the server's thread management; avoids creating disallowed pools. |
| Just need to point `@Async` to a JDK `Executor` bean by name | Can use that `Executor` bean directly | Spring lets `@Async("beanName")` reference an `Executor` bean; wrapping in an adapter is not mandatory. |

So why still use an adapter when `@Async` accepts an `Executor`? Because another component may require **the `TaskExecutor`/`AsyncTaskExecutor` interface specifically**, or you want to expose a uniform Spring bean while keeping resource configuration on the JDK executor. Do not automatically double-wrap every executor if the application has no need for it.

`ConcurrentTaskExecutor` has a constructor accepting an `Executor`, along with `setConcurrentExecutor(...)` and `getConcurrentExecutor()`. The no-arg constructor has been deprecated in recent Spring releases; prefer **passing the executor explicitly** so who creates and who owns the resource remain clear.

## 4. Complete Example: Sharing an ExecutorService with @Async

The example below runs with **Java 17+**, Maven, and **Spring Framework 6.2.12**. The system owns a configured JDK `ThreadPoolExecutor` and exposes it to Spring via `ConcurrentTaskExecutor`.

We intentionally pick a bounded queue to show that **the JDK pool itself** determines parallelism and backpressure. This pattern separates the JDK executor bean from the adapter bean; in a real application, the JDK bean might be provided by an infrastructure module or another integration component.

Directory structure:

```text
concurrent-executor-demo/
├── pom.xml
└── src/main/java/example/ConcurrentExecutorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>concurrent-executor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.ConcurrentExecutorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/example/ConcurrentExecutorDemo.java`:

```java
package example;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ConcurrentTaskExecutor;

public class ConcurrentExecutorDemo {

    public record WorkResult(String value, Thread executedBy) {
    }

    public static class WorkService {
        @Async("springExecutor")
        public CompletableFuture<WorkResult> process(String input) {
            // The method body runs on the selected executor via the Spring proxy.
            WorkResult result = new WorkResult(
                "processed:" + input,
                Thread.currentThread()
            );
            return CompletableFuture.completedFuture(result);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean(name = "externalPool", destroyMethod = "shutdown")
        public ExecutorService externalPool() {
            AtomicInteger threadIds = new AtomicInteger();
            ThreadFactory threadFactory = task ->
                new Thread(task, "external-pool-" + threadIds.incrementAndGet());

            return new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(16),
                threadFactory,
                new ThreadPoolExecutor.AbortPolicy()
            );
        }

        @Bean("springExecutor")
        public ConcurrentTaskExecutor springExecutor(
                @Qualifier("externalPool") ExecutorService rawExecutor) {
            return new ConcurrentTaskExecutor(rawExecutor);
        }

        @Bean
        public WorkService workService() {
            return new WorkService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ExecutorService raw = context.getBean(
                "externalPool", ExecutorService.class);
            ConcurrentTaskExecutor adapted = context.getBean(
                "springExecutor", ConcurrentTaskExecutor.class);
            WorkService service = context.getBean(WorkService.class);
            Thread caller = Thread.currentThread();

            CompletableFuture<WorkResult> handle = service.process("A");
            WorkResult result = handle.join();

            System.out.println("sameDelegate="
                + (adapted.getConcurrentExecutor() == raw));
            System.out.println("workerPrefix="
                + result.executedBy().getName().startsWith("external-pool-"));
            System.out.println("differentThread="
                + (result.executedBy() != caller));
            System.out.println("value=" + result.value());
        }
    }
}
```

From the `concurrent-executor-demo` directory, run:

```bash
mvn -q compile exec:java
```

Four lines printed by **the program** in order (Maven or library logs, if any, are not part of these four lines):

```text
sameDelegate=true
workerPrefix=true
differentThread=true
value=processed:A
```

### Step-by-Step Breakdown

1. `externalPool()` creates a **JDK** `ThreadPoolExecutor`: at most two workers, a queue holding 16 waiting tasks, and an `AbortPolicy` rejection policy. This bean is held by Spring and closed with `shutdown` when the context ends.
2. `springExecutor(rawExecutor)` creates a `ConcurrentTaskExecutor` referencing **the exact existing executor**. Comparing `getConcurrentExecutor() == raw` proves the adapter does not replace the delegate object.
3. `@EnableAsync` enables `@Async` processing using default proxy mode. `context.getBean(WorkService.class)` retrieves the Spring-managed bean; calling `process("A")` from `main` goes through the proxy.
4. `@Async("springExecutor")` identifies the executor bean unambiguously. The interceptor submits the work through the adapter to `externalPool`; a JDK worker executes the `process` body.
5. The worker builds `WorkResult` with its thread and returns `CompletableFuture.completedFuture(result)`. **Completing the Future inside the worker** does not mean the method body ran on the caller.
6. The caller holds `handle` and calls `join()` to get the value. If the task is not finished yet, `join()` blocks the caller; if already done, it retrieves it immediately. The check lines show identical delegates and an execution thread distinct from the caller under **this specific configuration**.
7. On exiting `try`, `AnnotationConfigApplicationContext.close()` triggers destruction of container-managed beans. The example already completed `join()`, so no unfinished work remains to wait for.

`Thread` is included in `WorkResult` solely to verify the example. In a real application, business responses should return business data, not references to threads.

### Why Is the Example Output Deterministic?

We **do not rely on log ordering across multiple workers**. The program waits for the single task via `join()` before printing. The pool is created with a `ThreadFactory` giving workers an explicit prefix; a `ThreadPoolExecutor` with two workers always dispatches work to a pool worker rather than running directly on the caller under `AbortPolicy`. Therefore, all four checks produce the stated values on a successful run.

If you replace `AbortPolicy` with `CallerRunsPolicy`, when the pool is overloaded a rejected task can run directly on the submitting thread. Then the assumption `differentThread=true` would no longer hold for every task. Distinguish controlled examples from behavior under other policies.

## 5. An Adapter Does Not Guarantee a Different Thread

The JDK `Executor.execute()` contract allows an executor to run tasks immediately on the caller. For instance, the following snippet can be placed in a Java method with the `spring-context` dependency:

```java
import java.util.concurrent.Executor;
import org.springframework.scheduling.concurrent.ConcurrentTaskExecutor;

Thread caller = Thread.currentThread();
Executor directExecutor = Runnable::run;
ConcurrentTaskExecutor adapter = new ConcurrentTaskExecutor(directExecutor);

adapter.execute(() ->
    System.out.println("sameThread="
        + (Thread.currentThread() == caller))
);
```

Output:

```text
sameThread=true
```

`Runnable::run` executes the task directly. The Spring adapter only delegates, so it creates no new thread. If an executor like this is used with `@Async`, the call can still execute immediately on the caller even though the method carries the annotation. The name `AsyncTaskExecutor` describes **an API capable of accepting asynchronous-style tasks**, not an independent guarantee of execution policy separate from the delegate.

Similarly, an `ExecutorService` with a single worker can run tasks asynchronously yet **cannot execute multiple tasks in parallel at the same time**. The queue may grow while only one worker processes items. To determine real concurrency, inspect the underlying executor, not just the adapter's type.

## 6. Submitting Tasks Directly and Observing Results

Beyond `@Async`, internal components can have an `AsyncTaskExecutor` or `ConcurrentTaskExecutor` injected and call it directly:

```java
// Snippet inside a method that received AsyncTaskExecutor executor.
executor.execute(() -> sendAuditSignal());

Future<String> answer = executor.submit(() -> fetchValue());
String value = answer.get();
```

This is an operational snippet, **not** a standalone Java program; `sendAuditSignal()` and `fetchValue()` are application-provided business methods. `Future.get()` requires handling `InterruptedException` and `ExecutionException`, and can block.

With `@Async` returning `CompletableFuture<T>`, stages are commonly chained:

```java
CompletableFuture<String> display = service.process("B")
    .thenApply(result -> "Result: " + result.value());
```

The snippet above assumes `WorkService service` from the main example is available. `thenApply` may run on the thread completing the stage or the thread that observes the completed stage; it **does not** guarantee running on a new pool. If using `thenApplyAsync`, explicitly decide which executor handles the next step; use the overload accepting an `Executor` to avoid unintentionally shifting work to the JDK common pool.

### Success, Failure, and Rejection

Three moments to distinguish:

- **Before accepting the task:** `ThreadPoolExecutor` may reject because the queue is full or it is shut down. When called through the Spring adapter, this failure is normally translated into `TaskRejectedException`. There is no valid `Future` for an unaccepted task.
- **While the task runs:** exceptions in the work are surfaced via `Future.get()` as `ExecutionException`, or via `CompletableFuture.join()` typically as `CompletionException`. A successful return from `submit()` should not be treated as business completion.
- **On cancellation/timeout:** `Future.cancel(...)` can request cancellation, yet actual termination depends on whether the task cooperates with interruption. Timing out while waiting for a result does not by itself force the worker to stop working.

With `@Async` methods returning `void`, there is no `Future` for the caller to inspect exceptions. If this signature is genuinely needed, configure an `AsyncUncaughtExceptionHandler` and proper error observability channels. For critical work, prefer a result handle and an idempotent/retry strategy or durable queue.

## 7. Who Configures, Who Owns, and Who Closes the Executor?

The most important question when using an adapter is **which component owns the delegate**.

`ConcurrentTaskExecutor` accepts an executor via constructor or setter. **The adapter does not manage the full lifecycle of the supplied executor on your behalf.** If the pool is created by the application, the application must have a shutdown policy when stopping. If the pool is shared across multiple components, one component must not arbitrarily call `shutdown` while others are still using it. If it is a Jakarta EE container-managed executor, allocation and shutdown typically belong to the container.

In the example above:

```text
ApplicationContext
  ├── externalPool : ExecutorService
  |      ├── 2 worker threads
  |      └── bounded queue(16)
  |            (Spring calls shutdown on context close because the bean has destroyMethod)
  |
  ├── springExecutor : ConcurrentTaskExecutor
  |      └── references externalPool, does not create a second pool
  |
  └── workService
         └── @Async("springExecutor") reuses externalPool
```

Plain `shutdown()` **stops accepting new tasks, yet does not automatically wait for all running tasks to finish**. If a controlled shutdown is needed, the pool's owner must define policies for `awaitTermination`, timeouts, interruption handling, unstarted work, and data that must be preserved. Our example closes the context after `join()`, making it simpler than production scenarios.

`ConcurrentTaskExecutor` also allows `setConcurrentExecutor(newExecutor)` to swap the delegate. Changing the delegate applies only to future submissions; tasks already submitted to the old executor are not migrated to the new one. Lifecycle of both pools must be coordinated before swapping in a live system; it is best to configure once at startup unless there is a clear operational requirement.

### ManagedExecutorService in Jakarta EE

In Jakarta EE environments, the Spring adapter can recognize `ManagedExecutorService` and adapt additional managed-task metadata. When obtaining the default executor from JNDI, `DefaultManagedTaskExecutor` is the specialized option. Follow the application server's threading policies; do not spin up a `ThreadPoolExecutor` yourself to bypass server thread management.

## 8. Load, Queue, and Monitoring Settings Must Be Evaluated at the Delegate

In the example, the pool is configured as:

```java
new ThreadPoolExecutor(
    2, 2, 0, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(16),
    threadFactory,
    new ThreadPoolExecutor.AbortPolicy()
);
```

This is a clearly bounded example, not an optimal size for every system.

- **Worker counts (`corePoolSize`, `maximumPoolSize`)** bound the JDK pool's concurrency. For blocking I/O work, parameter sizing differs from CPU-bound work; measure execution time, wait time, and real load.
- **The queue** holds unexecuted tasks; a long queue increases latency even though callers receive a `Future` quickly. `Executors.newFixedThreadPool` uses an unbounded queue capacity in standard implementations; avoid assuming it provides automatic backpressure to protect the system.
- **Rejection policy** governs behavior when no capacity remains. `AbortPolicy` throws an error; `CallerRunsPolicy` can force the caller to run the task, causing blocking and breaking the assumption of always using another thread; task-dropping policies require weighing business correctness.
- **Monitoring** must track active workers, queue depth, wait/run durations, error counts, and rejections from the delegate or appropriate metrics tooling. `ConcurrentTaskExecutor` does not itself expose all the metrics and pool tuning knobs of `ThreadPoolTaskExecutor`.

If the delegate is indeed a `ThreadPoolExecutor`, methods like `getActiveCount()`, `getPoolSize()`, and `getQueue().size()` only provide instantaneous snapshots that can change right after reading. Do not write tests assuming these metric values stay fixed under concurrent load.

## 9. TaskDecorator and Thread-Bound Data

`ConcurrentTaskExecutor.setTaskDecorator(TaskDecorator)` lets you wrap callbacks before execution, often used to carry correlation IDs/logging context or measure duration. However, the adapter **does not automatically propagate** all `ThreadLocal` values from caller to worker.

A proper decorator must:

1. Capture needed data **on the task-submitting side**.
2. Set that data on the thread running the task.
3. Clean up/restore state in `finally`, because a pooled worker may serve a different request next.
4. Avoid carrying expired request objects, the wrong user's `SecurityContext`, or non-thread-safe mutable objects.

When using `submit`, the callback seen by the decorator may be a wrapper like `FutureTask` rather than the original `Runnable`. `FutureTask` captures exceptions for the caller to observe via `get()`, so a decorator catching naively with `try/catch` around `runnable.run()` **may not see task exceptions**. Design separate logging/metrics for `Future` outcomes when needed.

Similarly, a transaction bound to the calling thread is not automatically transferred to the worker by the adapter or `@Async`. If transactional operations are needed in a background task, define transaction boundaries on the worker via the appropriate Spring mechanism; do not rely on an open transaction on the HTTP request thread.

## 10. Common Misconceptions

| Misconception | Consequence | How to address |
| --- | --- | --- |
| “Wrapping an `Executor` creates a new pool.” | Miscounting threads/resources or tuning in the wrong place. | Use `getConcurrentExecutor()` and inspect the delegate; the adapter delegates to the same instance. |
| “The adapter has Concurrent in its name so it must run on another thread.” | Direct `Executor` or `CallerRunsPolicy` can run on the caller. | Read the delegate's policy and check threads and overload behavior. |
| “Using `@Async` automatically routes through the adapter.” | Missing `@EnableAsync`, self-invocation, or wrong bean selection breaks expectations. | Call via Spring bean/proxy, specify `@Async("springExecutor")`, and check config. |
| “`submit()` returning a Future means the task has finished.” | Processing unready data or missing errors. | Use callbacks/composition or deliberate `get()`/`join()`. |
| “For cron schedules, use `ConcurrentTaskExecutor`.” | Lacks the `TaskScheduler` API for time-based scheduling. | Use `ConcurrentTaskScheduler` or `ThreadPoolTaskScheduler`. |
| “Changing the wrapper changes the queue and core size.” | Tuning has no effect. | Configure the underlying executor itself; if you want a Spring bean-style pool, consider `ThreadPoolTaskExecutor`. |
| “Shutting down the adapter automatically drains all running tasks.” | Incomplete tasks or improperly closed resources. | Assign clear ownership and call shutdown/await on the delegate owner. |
| “`ThreadLocal` is carried automatically by Spring.” | Lost trace/security context or leaked context across reused workers. | Use a decorator or suitable propagation tool, restoring in `finally`. |
| “Wrapping an `ExecutorService` is enough to handle overload.” | Growing queues, rejection errors, or blocked callers. | Bound resources, set policies, and monitor queue/rejections. |

### Scenario Before and After Adapting

**Before:** an infrastructure module already created `ExecutorService sharedExecutor` with its own policies. A Spring module wants an `AsyncTaskExecutor` and calls `submit(Callable<T>)`; writing a new Spring pool would fragment resource configuration and split load differently than intended.

**After:** the integration module creates **one** `ConcurrentTaskExecutor(sharedExecutor)` bean and injects it into the Spring component. The provider of `sharedExecutor` continues managing worker counts, queues, and shutdown. The Spring component calls through its interface and observes `Future`. Integration has a clean boundary without needing a second pool.

If the actual need is only `@Async` pointing to an `Executor` bean, you can omit the adapter and use `@Async("sharedExecutor")`: Spring supports selecting an `Executor` bean. Keep the adapter only when there is a concrete benefit from Spring's interface or integration management.

## 11. Self-Check Questions

**1. `ConcurrentTaskExecutor` is created with `Executor direct = Runnable::run`. Does calling `execute` guarantee running on a different thread?**

No. The delegate invokes `Runnable.run()` immediately; the task runs on the caller. The adapter does not alter execution policy.

**2. Why can `getConcurrentExecutor() == rawExecutor` be `true`?**

The adapter stores and uses the exact delegate passed in; it does not create an additional thread pool to replace it. Returning `true` proves object identity in the example.

**3. Is `ConcurrentTaskExecutor` required in order to specify `@Async("myJdkExecutor")`?**

Not necessarily. The name in `@Async` can reference an `Executor` bean. The adapter is useful when another API requires `TaskExecutor`/`AsyncTaskExecutor` or specific Spring integration features.

**4. The JDK executor's queue is full and `AbortPolicy` rejects a task. Does the adapter create an extra worker?**

No. The delegate decides rejection. The Spring adapter can translate the error under the `TaskRejectedException` contract; overload handling belongs in pool design and business logic.

**5. Can a `ConcurrentTaskExecutor` be used for cron scheduling?**

No. `SchedulingTaskExecutor` does not mean `TaskScheduler`. When a `ScheduledExecutorService` needs Spring's scheduling API, see `ConcurrentTaskScheduler`.

**6. There are two executor beans, one a JDK pool and one an adapter wrapping that same pool. Does that mean four threads if the pool has two workers?**

No. Two beans expose two API surfaces, yet there is only **one** two-worker JDK thread pool in the example. Thread counts can vary per pool policy; the adapter does not double the workers.

**7. `@Async("springExecutor")` runs in a worker, but does a callback after `thenApply` necessarily use that worker?**

No. `thenApply` may run on the thread completing the stage or the registering thread if the stage is already complete. If you need to pin a specific executor for a stage, use the `...Async(..., executor)` variant and pass the designed executor.

### Summary

When selecting an executor in Spring, identify **where an executor already exists**, **what API the Spring component needs**, **who owns the pool**, **how resources are bounded**, and **how results/errors are observed**. `ConcurrentTaskExecutor`'s job is to bridge interfaces to reuse the exact existing JDK executor; decisions about threads, queues, parallelism, and lifecycle remain in the delegate.

### References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor` model, executor types, and `@Async` integration.
- [Spring Framework — ConcurrentTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ConcurrentTaskExecutor.html): constructors, delegate, `execute`, `submit`, `setTaskDecorator`.
- [Spring Framework — TaskExecutorAdapter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html): basic adapter from JDK `Executor`.
- [Java 17 — Executor API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html) and [ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): execution contract, results, and shutdown.
