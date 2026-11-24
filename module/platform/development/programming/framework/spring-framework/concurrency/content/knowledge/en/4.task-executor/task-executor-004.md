# Obtaining CompletableFuture via submitCompletable() When Supported by Your Spring Version

## Goals and Scope

In Spring Framework, `TaskExecutor` provides a way to hand off work to an executor, while `AsyncTaskExecutor` extends it with the ability to submit tasks that produce results. Starting in **Spring Framework 6.0**, `AsyncTaskExecutor` offers two `submitCompletable(...)` overloads, allowing you to immediately obtain a `CompletableFuture` to await, combine results, handle errors, and build asynchronous processing pipelines.

After this lesson, you will:

- Identify **the exact version and interface** that provide `submitCompletable()`.
- Choose between the `Runnable` and `Callable<T>` overloads, and understand `Void`/`T` results and how exceptions flow into the future.
- Call `thenApply`, `thenCombine`, `exceptionally`/`handle`, and `join()` for their intended purposes.
- Build a runnable example with `ThreadPoolTaskExecutor`, distinguishing execution failures from task-submission rejections.
- Have a compatibility fallback if you are running Spring Framework **prior to 6.0**.
- Understand the limits of timeouts, cancellation, thread pools, and context propagation in Spring applications.

**Version used to run the examples:** JDK **17+**, Maven, **Spring Framework 6.1.3**. The feature was introduced in **Spring Framework 6.0**; version 6.1.3 is chosen to provide a concrete, reproducible dependency coordinate. If your project uses another version, read the corresponding Javadoc before applying.

## 1. Distinguishing TaskExecutor, AsyncTaskExecutor, and CompletableFuture

`org.springframework.core.task.TaskExecutor` extends `java.util.concurrent.Executor` with the core contract:

~~~java
void execute(Runnable task);
~~~

`execute` hands off a task for execution but **returns no result** to the caller. `AsyncTaskExecutor` is a **subinterface** of `TaskExecutor`. Starting in Spring 6.0, it declares two default methods:

~~~java
CompletableFuture<Void> submitCompletable(Runnable task);

<T> CompletableFuture<T> submitCompletable(Callable<T> task);
~~~

The declarations above are **API signatures**, not standalone Java files. The library returns a `CompletableFuture` representing successful completion, failure, or cancellation of the task. Calling `submitCompletable` **does not block waiting for the work's result**; however, the executor may still spend time during submission due to concurrency limits/rejection policies, and waiting with `join()` or `get()` will block the calling thread until a result arrives.

| Submission method | Interface / API | Return value | Can chain `thenApply` directly? |
| --- | --- | --- | --- |
| `execute(Runnable)` | `TaskExecutor` | `void` | No |
| `submit(Runnable)` | `AsyncTaskExecutor` | `Future<?>`, success result is `null` | Not directly |
| `submit(Callable<T>)` | `AsyncTaskExecutor` | `Future<T>` | Not directly |
| `submitCompletable(Runnable)` | `AsyncTaskExecutor`, **6.0+** | `CompletableFuture<Void>`, success result `null` | Yes |
| `submitCompletable(Callable<T>)` | `AsyncTaskExecutor`, **6.0+** | `CompletableFuture<T>` | Yes |
| `CompletableFuture.supplyAsync(supplier, executor)` | Java 8+ and any `Executor` | `CompletableFuture<T>` | Yes |

**Do not confuse interface names with compile-time capability:** a variable declared merely as `TaskExecutor executor` does not expose `submitCompletable` on its **static type**, even when the underlying instance is a `ThreadPoolTaskExecutor`. Declare/inject `AsyncTaskExecutor` or an appropriate implementation type.

~~~java
// Illustrates choosing variable types (place inside a class with appropriate imports).
TaskExecutor basic = pool;
basic.execute(() -> doWork()); // valid
// basic.submitCompletable(() -> "x"); // does not compile: TaskExecutor lacks this API

AsyncTaskExecutor async = pool;
CompletableFuture<String> result = async.submitCompletable(() -> "x");
~~~

This snippet only illustrates **compile-time typing**, assuming `pool` is a `ThreadPoolTaskExecutor` and `doWork()` exists on the enclosing class. It is not a standalone program.

### Check the Version Before Calling

| Spring Framework library version | Behavior to remember |
| --- | --- |
| **5.x** | `AsyncTaskExecutor` has `submit(...)` returning `Future`; **`submitCompletable(...)` does not exist yet**. |
| **6.0 and later** | Has `submitCompletable(Runnable)` and `submitCompletable(Callable<T>)`, both documented `Since: 6.0` in Javadoc. |
| **6.1/6.2** | Both overloads remain present; older `submit(...)` methods gained default implementations in 6.1, which **does not change** the `submitCompletable` baseline. |

Spring Framework 6.x requires Java 17 or newer. In Spring Boot projects, inspect **the actual Spring Framework version resolved in the dependency tree**, rather than guessing from a `spring-boot-starter` name or a blog post about Boot.

## 2. The Two Overloads: Runnable and Callable<T>

### 2.1. `Runnable`: Care About Completion Status, No Payload

~~~java
CompletableFuture<Void> saved = async.submitCompletable((Runnable) () -> {
    saveToDatabase();
});

saved.thenRun(() -> notifyUser());
~~~

The snippet above is **illustrative code**: `async`, `saveToDatabase()`, and `notifyUser()` belong to a concrete application. `Runnable.run()` returns no value; on success, `saved.join()` returns **`null`**, making `CompletableFuture<Void>` suitable for database writes, event dispatch, or audit logging. Casting `(Runnable)` can disambiguate complex lambdas; for a lambda body calling a single `void` method, Java usually infers it naturally.

### 2.2. `Callable<T>`: Task Returning a Result

~~~java
CompletableFuture<Integer> count = async.submitCompletable(() -> {
    return 21 * 2;
});

CompletableFuture<String> message =
        count.thenApply(value -> "count=" + value);
~~~

This is also a **fragment** inside a program that has an `async` variable. Because the lambda returns `int`, Java infers the `Callable<Integer>` overload with `T = Integer`; `count.join()` returns `42`, and `message.join()` returns `"count=42"`. Unlike `Supplier<T>`, `Callable<T>.call()` is permitted to declare **checked exceptions**; if the task throws an exception, the future completes **exceptionally**.

### 2.3. Result Path

~~~text
Caller
  |
  | async.submitCompletable(callable)
  v
AsyncTaskExecutor -----------------> executor / queue / worker
  |                                      |
  | returns CompletableFuture<T> right away  calls Callable.call()
  v                                      |
Caller does other work                   +-- succeeds --> complete(value)
  |                                      |
  +-- thenApply / thenCombine            +-- fails ----> completeExceptionally(error)
  |                                      |
  +-- join() / get() <------------------- future completion state
~~~

`submitCompletable` only creates a **channel to receive the result**. It does not promise that the task starts immediately, does not grow workers infinitely, and does not configure the thread pool on its own. Speed, thread names, queues, and rejection rules depend on the **implementing executor**.

## 3. Complete Runnable Example with Maven and Spring Framework 6.1.3

This example runs standalone with a `main` method, **without needing a Spring Boot server**, `@EnableAsync`, or `@Async`. It uses `ThreadPoolTaskExecutor` (which implements `AsyncTaskExecutor`), configuring a fixed two-worker pool and a bounded queue.

Project layout:

~~~text
submit-completable-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SubmitCompletableDemo.java
~~~

### 3.1. File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>submit-completable-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                    <mainClass>demo.SubmitCompletableDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-context` dependency brings in the Spring libraries required for `ThreadPoolTaskExecutor`. Maven downloads dependencies from configured repositories when network access is available. In an existing Spring application, use the project's version management rather than adding `spring-context` with a mismatched version.

### 3.2. File `src/main/java/demo/SubmitCompletableDemo.java`

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SubmitCompletableDemo {

    public static void main(String[] args) {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("lesson-");
        pool.initialize();

        try {
            AsyncTaskExecutor executor = pool;

            // Runnable: no return value.
            AtomicInteger counter = new AtomicInteger();
            CompletableFuture<Void> incremented =
                    executor.submitCompletable((Runnable) () -> {
                        counter.incrementAndGet();
                    });

            // Callable: each task returns a String.
            CompletableFuture<String> first =
                    executor.submitCompletable(() -> "Spring");
            CompletableFuture<String> second =
                    executor.submitCompletable(() -> "CompletableFuture");

            // Combine two independent results once both complete.
            CompletableFuture<String> combined = first.thenCombine(
                    second, (a, b) -> a + " + " + b
            );

            System.out.println("combined=" + combined.join());
            System.out.println("runnable-result=" + incremented.join());
            System.out.println("counter=" + counter.get());

            // Failure inside the task only; submit itself was accepted.
            CompletableFuture<Integer> failed =
                    executor.submitCompletable((Callable<Integer>) () -> {
                        throw new IllegalStateException("demo-failure");
                    });

            int recovered = failed.exceptionally(error -> -1).join();
            System.out.println("recovered=" + recovered);
        } finally {
            // When manually creating a pool outside the Spring container, shut it down yourself.
            pool.shutdown();
        }
    }
}
~~~

Inside `submit-completable-demo`, run:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the **Java program** (excluding any build-tool logs):

~~~text
combined=Spring + CompletableFuture
runnable-result=null
counter=1
recovered=-1
~~~

**Why is the output deterministic even though tasks run concurrently?** `thenCombine` completes only after both futures hold values; `combined.join()` awaits the combined result. `incremented.join()` waits for the increment operation to finish before reading `counter`. The failing future is converted by `exceptionally` to `-1` before printing. The actual execution order of the workers **is not fixed**; only the order of `println` statements in `main` is fixed.

**Why call `initialize()` and `shutdown()`?** This executor is constructed manually. `initialize()` sets up the internal executor; `shutdown()` ends the pool's lifecycle. When the same executor class is registered as a Spring bean, the Spring container manages its lifecycle.

**Why use `AtomicInteger`?** The task runs on another thread; `AtomicInteger` demonstrates safe shared updates. Even though the example increments only once, the habit of using thread-safe structures for shared state should always be maintained.

## 4. Composing CompletableFuture After Receiving It from submitCompletable

The advantage of `CompletableFuture` over plain `Future` is the ability to **build downstream processing stages** instead of merely calling `get()` to block for a result.

| Method | Role | Notes |
| --- | --- | --- |
| `thenApply(fn)` | Transform result `T -> U` after success | Non-`Async` callback; may run on the thread completing the future or the thread invoking the call |
| `thenCompose(fn)` | Chain a step returning `CompletionStage<U>`; avoids `Future<Future<U>>` | Useful for dependent tasks |
| `thenCombine(other, fn)` | Combine two independent tasks once both complete | Can run concurrently if the executor has available workers |
| `allOf(f1, f2, ...)` | Wait for all futures to finish | Returned future is `CompletableFuture<Void>`; read each individual result separately |
| `exceptionally(fn)` | Supply a fallback value when the chain fails | Does not run when the future succeeds |
| `handle((value, error) -> ...)` | Handle both success and failure | Can transform into another result |
| `whenComplete((value, error) -> ...)` | Observe/log completion | Not the primary way to recover errors; if the callback throws, the resulting stage fails |
| `join()` / `get()` | Wait and retrieve final result | Use at boundaries needing the value; avoid blocking inside workers |

Illustrative snippet **when an `async` variable of type `AsyncTaskExecutor` is already present**:

~~~java
CompletableFuture<Integer> price =
        async.submitCompletable(() -> 100);

CompletableFuture<Integer> tax =
        async.submitCompletable(() -> 10);

CompletableFuture<String> display = price
        .thenCombine(tax, Integer::sum)
        .thenApply(total -> "total=" + total);

System.out.println(display.join()); // total=110
~~~

Do not call `join()` immediately after submitting each task; doing so forces sequential waiting and defeats the benefit of composing independent work.

### `thenApply` vs. `thenApplyAsync`

`thenApply` makes no promise to use a separate executor. `thenApplyAsync(fn)` **without an executor argument** defaults to `ForkJoinPool.commonPool()` per the Java 17 `CompletableFuture` contract (runtime exceptions noted in JDK docs). If you want the next stage to run on the same Spring executor, pass it explicitly:

~~~java
CompletableFuture<String> next = async
        .submitCompletable(() -> "Spring")
        .thenApplyAsync(value -> value.toUpperCase(), async);
~~~

This is a fragment assuming `async` already exists. Passing the executor explicitly is useful when you need to control worker counts or apply a `TaskDecorator` to subsequent stages; however, avoid forcing every tiny transformation onto another thread since each scheduling step carries overhead.

## 5. Three Error Categories to Distinguish

### 5.1. Errors Inside the Callable/Runnable Body

If the task throws `IOException`, `IllegalStateException`, or another exception, the future **completes exceptionally** instead of holding a normal value. Example:

~~~java
CompletableFuture<Integer> failed =
        async.submitCompletable((Callable<Integer>) () -> {
            throw new IllegalArgumentException("invalid input");
        });

int value = failed.exceptionally(error -> 0).join(); // 0
~~~

Here casting `Callable<Integer>` resolves the overload for a lambda that only contains `throw`. Calling `join()` on an **unrecovered** failed future throws `CompletionException` (unchecked), while `get()` throws `ExecutionException` (checked); inspect `getCause()` to identify the original business exception. `get()` can also throw `InterruptedException`, so handle interrupt signals properly.

### 5.2. Executor Rejects the Task at Submit Time

`AsyncTaskExecutor.submitCompletable` is allowed to throw `TaskRejectedException` **immediately inside the submission call** when the executor rejects the task (for example, the pool has shut down or is overloaded per its configuration). This is a major difference from **errors occurring after the task has been accepted**.

~~~java
try {
    CompletableFuture<String> future =
            async.submitCompletable(() -> "ok");
    // A Future is only returned when the submit step succeeds.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Application decides on an overload response or bounded retry.
}
~~~

This code is an application fragment with `async`. Do not assume every failure enters `exceptionally(...)`: if submission **throws before returning a future**, there is no future to attach stages to. If you synthesize a fallback via `CompletableFuture.failedFuture(ex)`, do so explicitly at the API layer when business policy permits.

### 5.3. Errors in Downstream Callbacks

Even when `submitCompletable` succeeds, callbacks such as `thenApply(...)` or `thenCombine(...)` can still throw exceptions. When that happens, **the downstream stage's future** completes exceptionally. Attach `exceptionally` or `handle` at the right stage; if logging via `whenComplete`, record the cause as well, but do not treat `whenComplete` as automatic error recovery.

## 6. Fallback When Your Spring Version Lacks submitCompletable()

In **Spring Framework 5.x**, `AsyncTaskExecutor.submitCompletable` **does not exist**. Attempting to call it rightly produces a compilation error such as `cannot find symbol: method submitCompletable(...)`. Do not attempt to fix this by casting, because casting **does not add methods** to an older library's class.

Because `TaskExecutor` extends `java.util.concurrent.Executor`, you can use the JDK methods available since Java 8:

~~~java
// Fragment usable with TaskExecutor in Spring 5.x.
// taskExecutor is a configured TaskExecutor instance.
CompletableFuture<String> withValue =
        CompletableFuture.supplyAsync(() -> "result", taskExecutor);

CompletableFuture<Void> withSideEffect =
        CompletableFuture.runAsync(() -> System.out.println("saved"),
                                   taskExecutor);
~~~

This snippet is not a standalone class; it requires importing `java.util.concurrent.CompletableFuture` and having a `taskExecutor` variable. The second argument is **critical**: calling `supplyAsync(supplier)` or `runAsync(runnable)` **without passing an executor** makes the JDK choose `CompletableFuture`'s default executor, usually the common pool, rather than the Spring `TaskExecutor` you configured.

**Difference when adapting:** `supplyAsync` takes a `Supplier<T>`, not a `Callable<T>`; `Supplier.get()` does not declare checked exceptions. If the task must throw a checked exception, catch/wrap it inside the lambda or adjust the API accordingly. `runAsync` uses `Runnable`; both still produce a `CompletableFuture`, though this is a **compatibility workaround**, not `submitCompletable` existing in Spring 5.x.

In addition, if the actual implementation is `SyncTaskExecutor`, calling `CompletableFuture.supplyAsync(..., taskExecutor)` may **execute synchronously right on the caller** because the passed executor is not asynchronous. Do not infer concurrency solely from the `CompletableFuture` return type.

## 7. Integrating Into a Spring Application: Beans and Dependency Injection

In a real Spring application, instead of calling `new` on an executor per request, configure it as a **singleton bean**, then inject it using the `AsyncTaskExecutor` interface.

File `ReportExecutorConfig.java` in an application with Spring component scanning enabled (illustrative snippet, not a standalone runnable project):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ReportExecutorConfig {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("report-");
        return executor; // Spring manages initialize/destroy
    }
}
~~~

File `ReportService.java` in the same module:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final AsyncTaskExecutor executor;

    public ReportService(
            @Qualifier("reportExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> buildReport(String reportId) {
        return executor.submitCompletable(
                () -> "report:" + reportId
        );
    }
}
~~~

These two classes demonstrate wiring into an **existing Spring application**, not a standalone `main` program. The Spring container invokes initialization and cleanup hooks on the `ThreadPoolTaskExecutor` bean. When multiple executors exist, use `@Qualifier` or explicit bean selection to ensure the intended pool is used.

**Difference from `@Async`:** `submitCompletable` is a direct API call, so it **does not require `@EnableAsync`** and does not depend on a Spring AOP proxy. `@Async` is a separate mechanism: Spring intercepts method calls through a proxy to dispatch them to a configured executor. An `@Async` method can return `CompletableFuture`, yet not every `CompletableFuture` created by the application goes through `@Async`.

**Spring context:** transactions, security context, MDC, and request context are normally bound to a specific thread or scope. Never assume all contexts are copied into a new task. When needed, use framework-supported propagation mechanisms, `TaskDecorator`, or explicit data passing; clean up context in `finally`. Avoid mistaking a caller thread's DB transaction for a transaction that automatically spans background threads.

## 8. Common Production Pitfalls

### 8.1. `join()` Blocks and Can Starve a Pool

Consider a pool with **a single worker**: task A runs in the pool, submits task B into the **same pool**, and calls `B.join()`; B has no worker to run on while A holds the only worker waiting for B. This can cause a **thread-starvation deadlock**. Use asynchronous stages like `thenCompose`/`thenCombine` instead of waiting on child futures inside a worker, or adjust your architecture/executors.

### 8.2. Future Timeouts Do Not Automatically Stop Running I/O

`future.orTimeout(2, TimeUnit.SECONDS)` causes the **future to complete exceptionally** with a timeout if no result arrives within 2 seconds, but it **does not guarantee** stopping an ongoing HTTP request, SQL statement, or `Runnable`. Likewise, `completeOnTimeout(fallback, ...)` only updates the future's state on timeout; business side effects may still keep running.

`CompletableFuture.cancel(true)` also does not guarantee interrupting the thread executing the task: the `CompletableFuture` contract treats cancellation as exceptional completion, and the `mayInterruptIfRunning` flag **does not have the interrupting effect of `FutureTask`**. You still need timeouts on the HTTP client itself, JDBC/DB queries, and cooperative cancellation logic inside the task layer.

### 8.3. Backpressure and Rejection

`CompletableFuture` does not increase pool capacity. Tune `corePoolSize`, `maxPoolSize`, `queueCapacity`, and `RejectedExecutionHandler` for your workload, then monitor throughput, queue length, active count, and tail latency. When the queue is full, a task can be rejected synchronously; attaching `exceptionally` **only to the future** will not catch that submission failure.

With `ThreadPoolTaskExecutor`, the pool normally **prefers queuing** once core workers exist, only expanding up to max workers when the queue cannot accept more tasks. Therefore, a large `maxPoolSize` paired with a huge `queueCapacity` may create far fewer workers than you expect.

### 8.4. Which Thread Runs Callbacks?

`thenApply` is not guaranteed to run on the configured Spring worker; `thenApplyAsync` without an executor argument usually runs on `ForkJoinPool.commonPool()`. Whenever thread choice, MDC, or concurrency bounds matter, pass an explicit executor to `...Async` methods.

Which thread executes a callback also depends on when the future completes, so do not write tests asserting specific thread names for non-`Async` callbacks.

### 8.5. Masked Failures

If you submit a task and discard the future, exceptions may **go unobserved** by the caller. With `submitCompletable`, task failures are reflected in the future's state; attach handling stages, return the future upstream, or log/observe it with clear ownership. Do not rely solely on `Thread.UncaughtExceptionHandler` or executor logs to surface every exception from tasks managed by `Future`/`CompletableFuture`.

## 9. Choosing the Right API for the Problem

| Real-world need | Recommendation |
| --- | --- |
| Only need to trigger a `Runnable`, no completion tracking needed | `TaskExecutor.execute` |
| Need to await and get a result without chaining callbacks | `AsyncTaskExecutor.submit` returning `Future` |
| Need results, multi-task composition, pipeline error recovery; Spring 6.0+ | **`AsyncTaskExecutor.submitCompletable`** |
| Only have a `TaskExecutor` bean or running Spring 5.x | `CompletableFuture.supplyAsync/runAsync(..., taskExecutor)` |
| Want a Spring method to run automatically via proxy with `@EnableAsync` | Consider `@Async` and returning `CompletableFuture` |
| Mostly CPU-bound tasks | Pool sized to CPU resources; do not simply spawn more tasks/futures |
| I/O-bound tasks with limited downstream pools/connections | Bound downstream concurrency, add timeouts, backpressure, and load testing |

### Adoption Checklist

1. Verify the Spring Framework version resolved by your build is **6.0+** and check that the variable type is **`AsyncTaskExecutor`**.
2. Choose `Callable<T>` when you need a value, `Runnable` when you only need completion status.
3. Ensure the executor is initialized/container-managed; configure queue, workers, and rejection appropriately.
4. Chain `thenApply`/`thenCombine`/`exceptionally` along the data flow; only call `join` where synchronization is truly required.
5. Catch `TaskRejectedException` separately at **submit time**, and handle in-task exceptions through the future.
6. Implement real I/O timeouts, cooperative cancellation, context propagation, and pool monitoring.

## 10. Self-Check

**Q1.** With `TaskExecutor executor = new ThreadPoolTaskExecutor();`, can you call `executor.submitCompletable(...)` directly?  
**Answer:** No, because the static type `TaskExecutor` only declares `execute`. Use `AsyncTaskExecutor` or an appropriate implementation type.

**Q2.** Why does `CompletableFuture<Void>.join()` return `null` after a `Runnable` task succeeds?  
**Answer:** `Runnable` has no return value. The Future is used to track completion.

**Q3.** How does an already-accepted task throwing an exception differ from the pool rejecting it at submission?  
**Answer:** An exception inside the task completes the future exceptionally; rejection at submission can throw `TaskRejectedException` before any future is returned.

**Q4.** Why might `thenApplyAsync(fn)` bypass the Spring pool?  
**Answer:** Without an executor argument, the JDK uses the default async execution facility, specifically the common pool under the standard `CompletableFuture` contract.

**Q5.** If running Spring 5.3, what compatibility approach still lets you obtain a `CompletableFuture`?  
**Answer:** `CompletableFuture.supplyAsync(supplier, taskExecutor)` or `runAsync(runnable, taskExecutor)` using a configured `TaskExecutor` bean; do not call APIs introduced only in Spring 6.0.

**Q6.** Does `cancel(true)` on a `CompletableFuture` guarantee aborting an in-progress DB write?  
**Answer:** No. `CompletableFuture` cancellation does not guarantee interrupting the running task; real timeouts/cancellation are needed at the I/O and business layers.

## Official References

- [Spring Framework 6.1.3 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): signatures of both overloads, `Since: 6.0`, return types, and `TaskRejectedException`.
- [Spring Framework 6.1.3 — TaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskExecutor.html): base interface with only `execute(Runnable)`.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor, pool/queue, lifecycle, and rejection.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor, implementations, and differences from `@Async`.
- [Java SE 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion stages, callback execution threads, `join`/`get`, timeouts, and cancellation.
