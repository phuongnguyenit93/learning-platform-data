# `TaskExecutorAdapter`: Adapting the JDK `Executor` Contract in Spring

**Module:** Spring Framework - concurrency  
**Group:** Executor Selection  
**Topic:** `TaskExecutorAdapter` adapts the JDK `Executor` contract.

## 1. The Problem: You Have a JDK `Executor` and Want to Use It Through Spring's API

Many Java systems already have a task executor (`Executor` or `ExecutorService`) provided by another library, container, or infrastructure layer. Meanwhile, Spring code may want to interact via `TaskExecutor` or `AsyncTaskExecutor`, attach a `TaskDecorator`, and standardize how task rejections are reported. **`TaskExecutorAdapter` is the bridge class in the JDK → Spring direction**.

One way to picture it:

```text
Caller using Spring TaskExecutor / AsyncTaskExecutor
                      |
                      v
     TaskExecutorAdapter (adapter, holds no workers of its own)
                      |
                      v
        Existing JDK Executor / ExecutorService
                      |
                      v
       Actual threads/queue/scheduling of the delegate
```

The adapter instance **does not create a thread pool, decide worker counts, or durably persist jobs**. It forwards calls to the executor passed into its constructor. If the delegate runs tasks immediately on the calling thread, the adapter can also run synchronously; if the delegate has a thread pool, work runs according to that pool's schedule.

Illustrative example:

```java
Executor jdkExecutor = ...; // Executor that already exists in the application.
TaskExecutorAdapter springExecutor = new TaskExecutorAdapter(jdkExecutor);
springExecutor.execute(() -> doWork());
```

This is an **illustrative snippet**; you must declare `jdkExecutor`, `doWork()`, and import the corresponding types in your application. The core point is **keeping the delegate unchanged** while changing the interface used by the consumer.

### Why Not Use `Executor` Directly?

You *can* use a JDK `Executor` directly in many places in Spring: `TaskExecutor` extends the `Executor` contract, and many Spring integration points accept `Executor`. An adapter is useful when:

- An API specifically requires a Spring `TaskExecutor`/`AsyncTaskExecutor` object.
- You want `submit(Runnable)` or `submit(Callable<T>)` to return a `Future` even when the delegate is only an `Executor`.
- You want to apply a `TaskDecorator` at the task-dispatch boundary.
- You want rejection errors reported using Spring's `TaskRejectedException`.
- You want to reuse an existing executor without yet migrating the entire configuration to `ThreadPoolTaskExecutor`.

An adapter is an **integration choice**, not a mandatory step for every asynchronous use case.

## 2. Contracts to Distinguish

| Interface/class | What role does it play? | Notable capabilities |
| --- | --- | --- |
| `java.util.concurrent.Executor` | Basic JDK contract | `execute(Runnable)`, does not mandate creating new threads |
| `java.util.concurrent.ExecutorService` | Extended JDK contract | `submit`, `Future`, `shutdown`, awaiting termination, multi-task operations |
| `org.springframework.core.task.TaskExecutor` | Spring interface, also an `Executor` | `execute(Runnable)` under Spring's task-executor model |
| `org.springframework.core.task.AsyncTaskExecutor` | Spring interface extending `TaskExecutor` | `submit(Runnable)` / `submit(Callable<T>)` returning `Future` |
| `org.springframework.core.task.support.TaskExecutorAdapter` | Wraps a JDK `Executor` | Provides Spring's `AsyncTaskExecutor` by delegating or wrapping `FutureTask`, depending on the delegate |
| `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` | Executor configured and managed by Spring | Thread pool, queue, thread naming, lifecycle, Spring-friendly metrics/configuration |
| `org.springframework.core.task.support.ExecutorServiceAdapter` | Adapter in the **reverse direction** | Exposes a Spring `TaskExecutor` as a JDK `ExecutorService`; lifecycle still belongs to the real executor |

The name `TaskExecutorAdapter` can make it sound like a “pool-creation tool”; in reality it only performs **interface adaptation**. Nor should it be confused with `ExecutorServiceAdapter`: the two classes face opposite directions.

**Version note:** this lesson uses the stable APIs `execute`, `submit`, and `setTaskDecorator`. In the Spring Framework 6.2 line, `TaskExecutorAdapter` also implements `AsyncListenableTaskExecutor`; in Spring Framework 7, the interface hierarchy was simplified back to `AsyncTaskExecutor`. Do not rely on `submitListenable` when writing code meant to be portable across versions.

## 3. `execute(Runnable)`: Delegates Execution, Does Not Promise Another Thread

The JDK `Executor.execute` contract simply accepts a `Runnable` for the executor to handle; how it runs depends on the delegate:

```java
Executor inline = Runnable::run;
TaskExecutorAdapter adapter = new TaskExecutorAdapter(inline);

adapter.execute(() -> System.out.println("work"));
```

In this example, `Runnable::run` invokes `run()` **right on the current thread**, so `execute` behaves synchronously. If you swap the delegate for `Executors.newFixedThreadPool(2)`, the task is scheduled through the thread pool. The adapter does not change that fundamental behavior.

Several points to distinguish:

- Calling `execute()` **returns `void`**; there is no direct `Future` to retrieve a result.
- Do not assume the task has finished when `execute` returns; that is only true for inline delegates.
- If the executor rejects because it is shut down or full, the call may throw an error at submission time.
- Runtime errors **inside** the task happen when the task executes; if the task is on a worker thread, the exception does not automatically travel back to the request thread that called `execute`.
- Swapping the delegate for a new executor is a decision about workers, queues, parallelism, and backpressure policy; swapping the adapter alone does not accomplish that.

## 4. `submit`: Adding the `Future` Contract Even for a Plain `Executor`

`AsyncTaskExecutor` offers two submission forms:

```java
Future<?> done = adapter.submit((Runnable) () -> performAction());
Future<Integer> result = adapter.submit(() -> calculateValue());
```

This is an **illustrative snippet** requiring appropriate `performAction()` and `calculateValue()` methods. For `Runnable`, a successful `Future.get()` returns `null`; for `Callable<T>`, it returns a value of type `T`. An exception during execution is stored inside the `Future`; calling `get()` throws `ExecutionException` whose `getCause()` is the original error. `get()` blocks the calling thread until completion or failure.

Under the hood, `TaskExecutorAdapter` has two important branches:

1. **The delegate is an `ExecutorService` and no `TaskDecorator` is configured:** the adapter can directly call the delegate's `ExecutorService.submit(...)` and return the `Future` created by the delegate.
2. **The delegate is only an `Executor` or a `TaskDecorator` is set:** the adapter creates a `FutureTask`, submits this `Runnable` via `execute`, and returns the `FutureTask` to the caller. This lets an `Executor` that only has `execute` still support `submit`.

Typical path:

```text
submit(Callable<T>)
       |
       +-- ExecutorService + no decorator --> delegate.submit(callable)
       |
       +-- plain Executor / has decorator --> FutureTask(callable)
                                              |
                                              v
                                  delegate.execute(wrapped FutureTask)
                                              |
                                              v
                                   Future<T> for caller
```

Both branches still depend on the delegate: an inline executor completes the `Future` right on the calling thread; a pool may process slowly; an overloaded queue may reject.

### `Future` Does Not Automatically Turn a Task into a Long-Lived Job

`Future` represents a single computation **inside the running process**. It does not persist state to a database, automatically retry after a crash, or mean an HTTP client can query the result after the response ends.

If a controller calls `future.get()` right after `submit`, the controller thread still **waits** for the task to finish. Merely switching from `execute` to `submit` does not free request threads. Background processing and HTTP contracts must be designed separately.

## 5. Runnable Java 17 Example: Direct Executor, Pool, `submit`, Decorator, Rejection

The following complete example accurately demonstrates these properties:

- A **direct** delegate (`Runnable::run`) makes the adapter run synchronously as well.
- A JDK `ExecutorService` delegate with two workers and a bounded queue; the adapter accepts work and returns a `Future`.
- A `TaskDecorator` wraps callbacks to count task executions.
- A delegate rejects a task; the adapter reports Spring's `TaskRejectedException`.

Choose **JDK 17+**, Maven, and **Spring Core 6.2.12** for a version-pinned example. Structure:

```text
taskexecutor-adapter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── TaskExecutorAdapterDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>taskexecutor-adapter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/TaskExecutorAdapterDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.core.task.support.TaskExecutorAdapter;

public class TaskExecutorAdapterDemo {

    public static void main(String[] args) throws Exception {
        Thread callingThread = Thread.currentThread();

        // Valid JDK Executor, yet always runs immediately on the calling thread.
        Executor directExecutor = Runnable::run;
        TaskExecutorAdapter direct = new TaskExecutorAdapter(directExecutor);
        AtomicInteger sameThread = new AtomicInteger();

        direct.execute(() -> sameThread.set(
                Thread.currentThread() == callingThread ? 1 : 0));

        System.out.println("inline=" + (sameThread.get() == 1));
        System.out.println("inlineResult=" + direct.submit(() -> 6 * 7).get());

        // Real JDK pool: 2 workers, queue up to 8 waiting jobs.
        ExecutorService jdkPool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(8),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            TaskExecutorAdapter spring = new TaskExecutorAdapter(jdkPool);
            AtomicInteger decoratedRuns = new AtomicInteger();

            spring.setTaskDecorator(task -> () -> {
                decoratedRuns.incrementAndGet();
                task.run();
            });

            Future<Integer> answer = spring.submit(() -> 40 + 2);
            CountDownLatch signal = new CountDownLatch(1);
            spring.execute(signal::countDown);
            Future<?> noResult = spring.submit(() -> { });

            // Demo only: wait to produce deterministic output.
            System.out.println("poolResult=" + answer.get());
            if (!signal.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("execute task did not finish");
            }
            noResult.get();
            System.out.println("decorated=" + decoratedRuns.get());
        } finally {
            // The delegate owner manages shutdown, not the adapter.
            jdkPool.shutdown();
            if (!jdkPool.awaitTermination(10, TimeUnit.SECONDS)) {
                jdkPool.shutdownNow();
            }
        }

        Executor alwaysReject = task -> {
            throw new RejectedExecutionException("busy");
        };
        TaskExecutorAdapter rejecting = new TaskExecutorAdapter(alwaysReject);

        try {
            rejecting.execute(() -> { });
        } catch (TaskRejectedException ex) {
            System.out.println("rejected=TaskRejectedException");
        }
    }
}
```

Run in the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=TaskExecutorAdapterDemo
```

**Program stdout upon normal completion:**

```text
inline=true
inlineResult=42
poolResult=42
decorated=3
rejected=TaskRejectedException
```

Output explanation:

- `inline=true`: the adapter uses `Runnable::run`, running on the calling thread; a class name containing “TaskExecutor” does not guarantee asynchronicity.
- `inlineResult=42`: `submit(Callable)` still works even when the delegate only has `Executor.execute`. Because the delegate runs directly, the computation finishes before `submit` returns.
- `poolResult=42`: the JDK delegate has a worker pool; `Future.get()` waits for the result returned from a worker. Here the demo program **deliberately waits** to print deterministic output.
- `decorated=3`: three task submissions went through the same adapter after setting the decorator: `submit(Callable)`, `execute(Runnable)`, and `submit(Runnable)`. The decorator wrapped the callback in all three cases.
- `rejected=TaskRejectedException`: `RejectedExecutionException` from the delegate on submission is translated into Spring's exception. That is a *submission* failure, distinct from an error inside an accepted task.

`Future.get()` in the example is for verification and does not represent how to optimize HTTP latency. In a real application, avoid inadvertently blocking a request thread waiting on the same overloaded pool.

## 6. `TaskDecorator`: Wrapping Callbacks at the Execution Boundary

`setTaskDecorator(TaskDecorator)` lets you add logic **around task execution**, commonly used for tracing/metrics or propagating certain context from the submitting thread to the executing thread:

```java
TaskExecutorAdapter adapter = new TaskExecutorAdapter(jdkExecutor);

adapter.setTaskDecorator(task -> () -> {
    long started = System.nanoTime();
    try {
        task.run();
    } finally {
        long durationNanos = System.nanoTime() - started;
        metrics.record(durationNanos);
    }
});
```

This is an **illustrative snippet**: `jdkExecutor` and `metrics` are dependencies you must define in your application. The decorator wraps the `Runnable` executed by the adapter, **which may be an internal callback like `FutureTask`**, not necessarily the raw Runnable/Callable passed by the user.

When propagating a `ThreadLocal`, capture the value on the **task-submitting thread** during `decorate`, then set and restore the old value on the **worker thread** inside `run`:

```java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static org.springframework.core.task.TaskDecorator traceDecorator() {
    return task -> {
        String captured = TRACE_ID.get(); // Task-submitting thread.
        return () -> {
            String previous = TRACE_ID.get(); // Worker thread.
            try {
                if (captured == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(previous);
                }
            }
        };
    };
}
```

This is an **illustrative method snippet** that must be placed inside a class with a corresponding `TRACE_ID` field. In production applications, prefer the official context-propagation mechanism of your stack and avoid copying sensitive data into a pool manually. Do not confuse trace/MDC propagation with carrying along a database transaction; transactions are bound to threads and the transaction manager and must not be arbitrarily cloned onto workers.

### Exceptions in a Decorator: `execute` Differs from `submit`

With `submit`, the callback seen by the decorator may be a `FutureTask`: `FutureTask.run()` **retains exceptions inside the Future**, rather than throwing them out of `run()` for the wrapper to catch. Thus:

```java
// Not sufficient to conclude every Callable succeeded.
adapter.setTaskDecorator(task -> () -> {
    try {
        task.run();
    } catch (Exception ex) {
        logFailure(ex);
        throw ex;
    }
});
```

This is only an **illustrative snippet** with `logFailure` undefined. With `submit`, a failing `Callable` can still let `task.run()` return normally from the decorator's perspective, while `future.get()` throws `ExecutionException`. Design error reporting around the `Future`/completion handler contract or explicit reporting inside the worker; do not rely on a decorator `catch` to trap all business errors.

## 7. From JDK Rejection to Spring Exceptions

A `ThreadPoolExecutor` can reject tasks when shut down or when exceeding its configured admission capacity. Under `AbortPolicy`, the JDK throws `RejectedExecutionException`. `TaskExecutorAdapter` catches submission-time failures and translates them to `TaskRejectedException` to match Spring's contract.

```text
Spring caller
    |
    | adapter.execute(task) / submit(task)
    v
JDK delegate accepts task?
    |
    +-- Yes --> task queued/runs --> succeeds or fails internally inside task
    |
    +-- No  --> RejectedExecutionException
                       |
                       v
                  TaskRejectedException
```

**Distinguish the two errors:**

- **Rejection:** the executor refused the work; with `AbortPolicy` this occurs immediately at `execute`/`submit`. The caller can react: return `503`/`429` depending on protocol, route to another queue, or report system busy.
- **Execution failure:** the task was accepted but failed while running; with `submit`, errors are observed via `Future.get()`/completion handling. Never automatically retry operations with side effects without an idempotency strategy.

Some JDK `RejectedExecutionHandler` policies **do not throw errors**: `CallerRunsPolicy` can execute the task directly on the submitting thread (unless the executor has shut down). In that case the adapter cannot infer that the task was rejected, and the request thread may block for a long time. Choose a policy based on backpressure needs and response guarantees rather than assuming the adapter always throws `TaskRejectedException`.

## 8. Integrating into Spring: An Adapter Bean Around a JDK Pool

An application with a JDK executor already used by another library can expose an adapter as a Spring bean. Here is a **two-file** example in a Spring Boot application using Spring Framework 6.x:

**`AsyncExecutorConfig.java`** (placed in an application package, e.g., `com.example.jobs`):

```java
package com.example.jobs;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.support.TaskExecutorAdapter;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncExecutorConfig {

    @Bean(name = "jdkBusinessPool", destroyMethod = "shutdown")
    public ExecutorService jdkBusinessPool() {
        return new ThreadPoolExecutor(
                2, 4, 30L, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(100),
                new ThreadPoolExecutor.AbortPolicy());
    }

    @Bean("businessExecutor")
    public AsyncTaskExecutor businessExecutor(
            @Qualifier("jdkBusinessPool") ExecutorService jdkPool) {
        return new TaskExecutorAdapter(jdkPool);
    }
}
```

Here:

- `jdkBusinessPool` is the **actual backend executor**, with up to 4 workers and 100 queue slots; `AbortPolicy` rejects when capacity is exhausted.
- `businessExecutor` is merely a Spring object wrapping that delegate. The program does not have *two* thread pools.
- `destroyMethod="shutdown"` applies to **the bean owning the `ExecutorService`**. The adapter is not an `ExecutorService` and does not provide a `shutdown()` lifecycle on the delegate's behalf.
- The bean configuration is a standalone wiring example; place it in an appropriately configured application and avoid creating multiple executors with overlapping roles.

**`ReportService.java`**:

```java
package com.example.jobs;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("businessExecutor")
    public CompletableFuture<String> createReport(String reportId) {
        String artifactId = "report-" + reportId;
        return CompletableFuture.completedFuture(artifactId);
    }
}
```

This is a **class file in a Spring application**, not a standalone program with `main`. With `@EnableAsync`, public calls going through the Spring proxy to `ReportService.createReport` are dispatched to the named executor bean. `CompletableFuture.completedFuture(...)` inside is the result computed by the worker; the future received by the caller represents the Spring-managed asynchronous invocation.

**Two important limitations:**

1. Calling `this.createReport(...)` from `ReportService` itself **does not go through the proxy** in default proxy mode, so `@Async` may not take effect. Call from another Spring bean, or use an appropriate invocation structure.
2. Returning a future from `@Async` does not durably persist jobs. If the process stops, tasks sitting in an in-memory queue can be lost. For critical tasks, you need a persistent state store/queue and a recovery mechanism.

If an application already uses `ThreadPoolTaskExecutor`, you normally just use that bean directly for `@Async`. Choose `TaskExecutorAdapter` when you genuinely need to **consume an existing JDK executor** or deliberately expose a Spring interface.

## 9. Ownership and Lifecycle: Who Closes the Pool?

What happens when calling:

```java
ExecutorService jdkPool = java.util.concurrent.Executors.newFixedThreadPool(2);
TaskExecutorAdapter adapter = new TaskExecutorAdapter(jdkPool);
```

`adapter` **does not become the default owner** of `jdkPool`. The adapter has no `shutdown()` API like `ExecutorService` and does not automatically close the pool when the adapter object becomes unreferenced. The component that created/registered the pool must manage `shutdown` per the application's contract.

If writing plain Java: use `try/finally`, shut down, and await workers when possible. In Spring IoC: register the backend as a bean with a destroy method or use a Spring executor with built-in lifecycle.

**Do not close the pool on every request**: a shared executor serves many requests; shutting down after the first request will cause subsequent requests to be rejected. Conversely, creating a new executor on every controller call without closing it can leak threads and exhaust resources.

`ExecutorServiceAdapter` (Spring → JDK) is a different class: it exposes a JDK interface over an underlying `TaskExecutor`. Per that class's contract, lifecycle still belongs to the backend; shutdown operations on the reverse adapter are no substitute for managing the backend.

## 10. Choose the Adapter or `ThreadPoolTaskExecutor`?

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| Already have a library/app-managed JDK `ExecutorService`, need Spring interface | `TaskExecutorAdapter` | Reuses the exact existing pool without changing ownership |
| Only have a JDK `Executor`, yet callers need `submit`/`Future` | `TaskExecutorAdapter` | Provides appropriate `FutureTask` support via the `AsyncTaskExecutor` contract |
| New Spring project, want pool/queue/thread naming/lifecycle configured via Spring beans | `ThreadPoolTaskExecutor` | Clear configuration and container-managed lifecycle |
| Need scheduled or cron task execution | `TaskScheduler`/appropriate scheduler | The adapter does not provide scheduling capabilities |
| Need an executor from a container or external library with special standards | Check that integration's adapter; `TaskExecutorAdapter` may work | Respect container ownership and rules first |
| Need durable job processing across restarts and multiple instances | DB/broker + workers | The adapter only forwards calls within a single process |
| Only a few `execute` calls via `Executor` and Spring APIs already accept `Executor` | Can use JDK `Executor` directly | No need for an extra wrapper without practical benefit |

Some Spring classes like `ConcurrentTaskExecutor` also support adapting JDK executors with `spring-context` conveniences; that is another option in the scheduling/concurrency layer. Do not stack multiple adapter layers if one existing bean already satisfies the contract.

## 11. Common Implementation Mistakes

### 11.1. Thinking the Adapter Creates New Threads Automatically

```java
TaskExecutorAdapter adapter = new TaskExecutorAdapter(Runnable::run);
adapter.execute(() -> longOperation());
```

This is an **illustrative snippet**, with `longOperation()` defined by you. This task runs immediately on the calling thread. If you want background execution, choose a delegate executor that actually processes on another worker.

### 11.2. Calling `submit` and Immediately Calling `get()` in a Controller

`Future<T>` is not a signal that a background task is decoupled from the HTTP lifecycle. `get()` can hold the HTTP thread until the worker finishes. If you need to return the result in the same response, use Spring MVC/WebFlux async request mechanisms; if you need to return `202 Accepted` and track later, design job IDs, status, retries, and storage.

### 11.3. Unbounded Queues or Unhandled Rejections

`Executors.newFixedThreadPool(n)` uses a queue bounded only by available memory, so capping **worker count** is not the same as capping **pending backlog**. For real workloads, consider a `ThreadPoolExecutor` with a bounded queue, an explicit handler, and monitoring of queue depth, rejected counts, and latency.

### 11.4. Treating Errors Inside `Future` Like Submission-Time Exceptions

`execute`/`submit` can be rejected immediately. However, a task accepted and later failing is observed on the execution path or when accessing `Future`. With `submit`, handle `ExecutionException` or appropriate callbacks. `TaskDecorator` only wraps the execution callback and does not guarantee catching all exceptions inside `FutureTask`.

### 11.5. Trying to “Propagate Transactions” via a Decorator

A `ThreadLocal` trace ID can be propagated safely with proper capture/restore/cleanup design. However, a database transaction is bound to resources and the transaction manager; never copy it to a worker by copying thread context. Workers updating the DB must open transactions per business requirements, and you must account for whether tasks are enqueued before or after commit.

### 11.6. Forgetting Self-Invocation with `@Async`

`@EnableAsync` in proxy mode does not intercept internal calls via `this`. Before blaming the adapter, verify the method is invoked through the Spring proxy, the executor bean name matches, and the service is actually Spring-managed.

### 11.7. Using Multiple Adapters and Thinking You Have Independent Pools

Two `TaskExecutorAdapter` instances pointing to the same `ExecutorService` still share the exact same workers/queue and affect each other's load. To isolate critical work, use separate delegate executors with dedicated sizing and backpressure policies.

### 11.8. Closing the Delegate from a Non-Owner

If an executor is shared, one component calling `shutdown()` can break all other consumers. Clearly identify the pool creator, bean scope, and shutdown timing in the application lifecycle.

## 12. Self-Check Questions and Exercises

**Question 1.** `TaskExecutorAdapter` receives `Executor direct = Runnable::run`. Does `adapter.submit(() -> 42)` actually run asynchronously?  
**Answer:** No. The delegate runs `Runnable` on the calling thread, so `FutureTask` completes while `submit` is running; the adapter does not force new thread creation.

**Question 2.** Why can `TaskExecutorAdapter` perform `submit(Callable)` even when the delegate only has `execute(Runnable)`?  
**Answer:** The adapter can wrap `Callable` in a `FutureTask` and pass that `FutureTask` to `Executor.execute`. `FutureTask` is both a `Runnable` and a `Future`.

**Question 3.** If the delegate is an `ExecutorService`, does the adapter always call `executorService.submit`?  
**Answer:** No. Without a decorator, the adapter can delegate directly; with a decorator, the adapter may wrap the task in a `FutureTask` to run through the decorator/`execute` path.

**Question 4.** In Spring, who should shut down the wrapped JDK executor?  
**Answer:** The component/bean owning the delegate; `TaskExecutorAdapter` itself does not replace the lifecycle of `ExecutorService`.

**Question 5.** Why might a decorator `try { task.run(); } catch (...)` fail to see errors from a `Callable` submitted via `submit`?  
**Answer:** The callback may be a `FutureTask`; it catches the `Callable`'s error and stores it so `Future.get()` throws `ExecutionException`, instead of letting the error escape `run()`.

**Question 6.** Three Spring replicas share one DB. Does wrapping the JDK pool with `TaskExecutorAdapter` protect cross-replica data consistency?  
**Answer:** No. The adapter only concerns submitting tasks to an in-JVM executor; DB/distributed boundaries require transactions, locking/versioning, idempotency, or appropriate architecture.

### Short Exercises

1. Replace the direct `Runnable::run` delegate with `Executors.newSingleThreadExecutor()`. Use a `CountDownLatch` to confirm work runs on a different thread and **remember to close the delegate**.
2. Add a decorator that counts tasks and sequentially submit `execute`, `submit(Runnable)`, and `submit(Callable)`. Why might the wrap count differ from the successful task count?
3. Create a `ThreadPoolExecutor` with 1 worker, a 1-element queue, and `AbortPolicy`; keep the worker busy with a latch, add a task to the queue, then try submitting a third task. Observe `TaskRejectedException` when the pool cannot accept more work. Clean up the latch/pool in `finally`.
4. In a Spring application, expose an `AsyncTaskExecutor` bean using `TaskExecutorAdapter` around a JDK pool. Use `@Async("...")` on a service called by **another bean** and observe the thread; try an internal call to see the proxy effect.

## 13. Key Takeaways

`TaskExecutorAdapter` **adapts contracts** between Spring and the JDK; the backend executor still decides when and on which thread tasks run, whether queue space exists, and when to shut down.

- **`execute`** forwards a `Runnable` to the delegate.
- **`submit`** returns a `Future`, delegating through `ExecutorService.submit` when appropriate or using `FutureTask` when needed.
- **`TaskDecorator`** wraps callbacks, useful for metrics/context; `Future` exceptions must be handled via the appropriate contract.
- **Rejection** can be represented by `TaskRejectedException`, while errors in already-running tasks must be tracked separately.
- **No automatic guarantees** of async threads, durability, retries, isolation, transactions, or lifecycle exist merely from using an adapter.

Official documentation for API reference:

- [Spring Framework 6.2 — `TaskExecutorAdapter` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html).
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
- [Spring Framework 6.2 — `AsyncTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html).
- [Java SE 17 — `Executor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html).
- [Java SE 17 — `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- [Java SE 17 — `FutureTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html).
- [Spring Framework 7 — `TaskExecutorAdapter` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html).