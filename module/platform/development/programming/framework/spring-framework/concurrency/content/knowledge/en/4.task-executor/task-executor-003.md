# AsyncTaskExecutor and the submit() Methods

> **Topic:** Spring Framework – concurrency  
> **Knowledge Area:** TaskExecutor  
> **Objective:** Understand the `AsyncTaskExecutor` contract, choose properly between `execute()`, `submit(Runnable)`, and `submit(Callable<T>)`, track results via `Future`, and manage errors, cancellation, timeouts, and resources when using executors in a Spring application.

## 1. Where Does AsyncTaskExecutor Sit in the Executor Ecosystem?

Java provides `java.util.concurrent.Executor` with `execute(Runnable)`; Spring declares `org.springframework.core.task.TaskExecutor` as an `Executor`-compatible abstraction. The general `TaskExecutor` contract permits multiple execution strategies, including synchronous execution on the caller thread (such as `SyncTaskExecutor`).

`org.springframework.core.task.AsyncTaskExecutor` **extends `TaskExecutor`**, adding the ability to submit tasks and receive a `Future` or `CompletableFuture` to observe results. Under the interface contract, `execute(Runnable)` on an `AsyncTaskExecutor` executes the task **asynchronously on a thread other than the caller**, rather than running the `Runnable` immediately on the caller thread. Even so, **the submit call itself** may have to wait according to the implementation's concurrency-limiting policy or be rejected when the executor is overloaded; you must not assert that every `submit` call always returns instantaneously.

~~~text
java.util.concurrent.Executor
            ^
            |
      Spring TaskExecutor
         |         |
         |         +-- SyncTaskExecutor (synchronous TaskExecutor)
         |
         +-- AsyncTaskExecutor
                   |
                   +-- SimpleAsyncTaskExecutor
                   +-- ThreadPoolTaskExecutor
                   +-- ConcurrentTaskExecutor / TaskExecutorAdapter
                   +-- other implementations
~~~

Note: The diagram illustrates **interface relationships and example implementations**, not the complete Java inheritance hierarchy across all classes.

`AsyncTaskExecutor` **is not** an `ExecutorService`. Although both share two `submit` overloads, the Spring interface does not include `invokeAll()`, `invokeAny()`, `shutdown()`, or the `submit(Runnable, T result)` overload from JDK `ExecutorService`. Lifecycle management is normally handled by Spring beans and concrete implementations.

## 2. Core Methods: execute or submit?

| Call | Input type | Return type | Meaning |
| --- | --- | --- | --- |
| `execute(Runnable)` inherited from `TaskExecutor` | Work with no declared return value | `void` | Only requests execution; no `Future` from this call to await or collect errors |
| `submit(Runnable)` | `Runnable` with `void run()` | `Future<?>` | Receives a handle to track completion; `get()` returns **null** on success |
| `submit(Callable<T>)` | `Callable<T>` with `T call()` | `Future<T>` | Receives a handle to track completion and retrieve the value returned by `call()` |
| `submitCompletable(Runnable)` | `Runnable` | `CompletableFuture<Void>` | Added in Spring Framework **6.0**; convenient for chaining processing steps |
| `submitCompletable(Callable<T>)` | `Callable<T>` | `CompletableFuture<T>` | Added in Spring Framework **6.0**; receives value and composition API |

The two `submit` overloads have existed in Spring for a long time; starting in **Spring Framework 6.1**, the interface provides default implementations that conceptually wrap an appropriate task and delegate to `TaskExecutor.execute(Runnable)`. Implementations can still override submission behavior; `ThreadPoolTaskExecutor` has its own overrides. Do not rely on a specific `Future` implementation class in business code.

The word "async" here describes the **execution model**. Meanwhile, `Future` is a **representation of a future result/state**. A successful `submit` only proves the executor **accepted** the task; it does not assert that the task has started, completed, or succeeded in business terms.

### 2.1. submit(Runnable): Execute Work Without a Return Value from run()

~~~java
Future<?> future = executor.submit(() -> {
    auditWriter.writeEntry("user-42", "LOGIN"); // illustrates an application dependency
});

// Wait until the Runnable finishes or reports failure:
Object result = future.get(); // null if the Runnable succeeds
~~~

This is an **application integration snippet** that already has an `executor` variable of type `AsyncTaskExecutor` and `auditWriter`; it is not a standalone compilable program. Use `Runnable` when the task performs an action and the caller only needs completion status. After `get()` returns normally, `result == null` is expected; there is no return data from `void run()`.

### 2.2. submit(Callable<T>): Receive a Typed Result

~~~java
Future<Integer> totalFuture = executor.submit(() -> {
    return 10 + 20;
});

int total = totalFuture.get(); // 30
~~~

`Callable<T>` can return `T` and declare `throws Exception`. The type `T` is inferred from the lambda/assignment; `Future<Integer>` gives compile-time type checking. When you want to return a value (aggregating stats, reading data, computing a score), this is the overload to choose.

**Common lambda overload pitfall:** an expression lambda like `() -> counter.incrementAndGet()` can be compatible with both `Runnable` and `Callable<Integer>`, causing confusion or overload ambiguity. When `Runnable` is intended, write a non-value-returning block `() -> { counter.incrementAndGet(); }`, or cast explicitly to `(Runnable)`.

### 2.3. How execute(Runnable) Differs from submit(Runnable) on Error Observation

~~~java
executor.execute(() -> doWork());      // no Future from execute()
Future<?> future = executor.submit(() -> doWork()); // returns a handle
~~~

With `submit`, failures occurring **inside the task** are normally captured inside the `Future`. If you never observe `Future.get()` or another tracking mechanism, errors can go unnoticed. With `execute`, how uncaught exceptions are reported/logged depends on the implementation, thread, and error handling. Both can throw an exception **at submission time**, such as `TaskRejectedException`.

## 3. Lifecycle of a Future

Picture `Future` as a receipt for a task:

~~~text
Caller                       AsyncTaskExecutor                 Worker thread
  | submit(Runnable/Callable)       |                                |
  |------------------------------->| check pool / queue              |
  |                                | may ACCEPT or REJECT            |
  |<----- Future (if accepted) ----|                                |
  |                                |------------ run task --------->|
  | do other work                  |                                |
  | future.get()                   |                         compute / fail
  | ... may have to wait ...       |                                |
  |<------------------------- result / failure / cancelled <---------|
~~~

JDK `Future` APIs to understand:

- `get()`: **waits** for the task to finish and retrieves the result. If the task failed, throws `ExecutionException` whose `getCause()` is the original error. If the task was cancelled, throws `CancellationException` (unchecked). If the waiting thread is interrupted, throws `InterruptedException`.
- `get(timeout, unit)`: waits **at most** the specified duration. Throws `TimeoutException` when **the wait times out**, and does not automatically cancel the running task. If you want to cancel, decide whether to call `cancel(...)` and accept that it is best effort.
- `isDone()`: `true` when the Future has ended in some way: **success, failure, or cancellation**. It is **not synonymous with success**.
- `isCancelled()`: marks that the task was cancelled under the Future contract.
- `cancel(false)`: requests cancellation; an already running task is normally allowed to continue without an interrupt request.
- `cancel(true)`: requests an interrupt if the task is running and the implementation knows the worker thread. It **does not guarantee** immediate stopping, database rollback, recalling a sent email, or terminating all I/O.
- **Memory visibility:** under the JDK `Future` contract, actions in the task *happen-before* actions following the corresponding `Future.get()` in another thread. This explains why you can safely read a result updated by the task after waiting on `get()`; it does not make all shared mutable state across the system thread-safe.

A task may run and finish before the caller even receives the `Future` reference; that is normal. Likewise, an incomplete `Future` does not indicate whether the task is sitting in the queue or actively running unless the implementation exposes additional metrics.

## 4. Spring Framework 6.2.x, Java 17+ Example: Both submit() Overloads Working

This example creates a `ThreadPoolTaskExecutor` as a Spring bean, retrieves it via the **`AsyncTaskExecutor` interface**, and submits three tasks: a `Runnable`, a `Callable<Integer>`, and a failing `Callable<Integer>` to observe `ExecutionException`. It does not use `@Async`, because tasks are submitted **directly** to the executor; `@EnableAsync` is not needed.

Create a Maven project:

~~~text
spring-submit-demo/
├── pom.xml
└── src/main/java/demo/SubmitDemo.java
~~~

**pom.xml** (Spring Framework 6.2.9 chosen for a concrete version; requires JDK 17+ and Maven):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-submit-demo</artifactId>
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

**src/main/java/demo/SubmitDemo.java**

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class SubmitDemo {

    @Bean
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("lesson-");
        return pool;
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(SubmitDemo.class)) {

            AsyncTaskExecutor executor =
                context.getBean(AsyncTaskExecutor.class);
            AtomicInteger counter = new AtomicInteger();

            // Void block: compiler chooses submit(Runnable).
            Future<?> action = executor.submit(() -> {
                counter.incrementAndGet();
            });

            // Value-returning expression: compiler chooses submit(Callable<Integer>).
            Future<Integer> calculation = executor.submit(() -> 7 * 6);

            // Catch error from an accepted Callable.
            Future<Integer> failure = executor.submit(
                (Callable<Integer>) () -> {
                    throw new IllegalStateException("simulated failure");
                }
            );

            System.out.println("Runnable result = " + action.get());
            System.out.println("Counter = " + counter.get());
            System.out.println("Callable result = " + calculation.get());
            System.out.println("Callable done = " + calculation.isDone());

            try {
                failure.get();
            } catch (ExecutionException ex) {
                System.out.println("Cause = " + ex.getCause().getMessage());
            }
        }
    }
}
~~~

Run from the `spring-submit-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SubmitDemo
~~~

Lines **printed by the program itself**, with deterministic order and values:

~~~text
Runnable result = null
Counter = 1
Callable result = 42
Callable done = true
Cause = simulated failure
~~~

Why this is deterministic:

1. `action.get()` waits for the `Runnable` to finish; a `Runnable` returns no value, so it prints `null`. The `AtomicInteger` update has completed before printing `Counter = 1`.
2. `calculation.get()` waits for `Callable<Integer>` and receives `42`. After `get()`, `isDone()` is guaranteed to be `true`.
3. `failure.get()` throws `ExecutionException`; `getCause()` is `IllegalStateException` with the deterministic message. This Future does not crash the program because it is caught.
4. Two workers may execute the three tasks in different orders, yet because the caller explicitly awaits and prints sequentially, **the output content and order remain fixed**.
5. Closing `AnnotationConfigApplicationContext` via try-with-resources ends the bean lifecycle; `ThreadPoolTaskExecutor` is a managed Spring bean with a shutdown mechanism. Production code must still configure the policy for completing pending tasks during shutdown.

This is a small example of **calling patterns and Future semantics**, not a guarantee for retries, transactions, surviving restarts, or full distributed business workflows.

## 5. Handling Errors Properly at Two Different Times

**At task submission time:**

~~~java
Future<String> future;
try {
    future = executor.submit(() -> externalClient.fetchResult());
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Pool closed or overloaded: no Future yet to track.
    throw ex;
}
~~~

This is an **illustrative integration snippet**, requiring `executor` and `externalClient` variables in the application. If the caller prefers avoiding a Spring-specific exception dependency, `TaskRejectedException` is also a `RejectedExecutionException` in the modern API.

**After the task is accepted:**

~~~java
try {
    String result = future.get(2, java.util.concurrent.TimeUnit.SECONDS);
    processResult(result);
} catch (java.util.concurrent.TimeoutException ex) {
    // WAIT timeout expired; the task is not automatically cancelled.
    future.cancel(true);  // Best effort; consider side effects.
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable originalFailure = ex.getCause();
    recordTaskFailure(originalFailure);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw ex;
} catch (java.util.concurrent.CancellationException ex) {
    recordCancellation(ex);
}
~~~

This is also an **application integration snippet**, placed inside a method declaring `throws InterruptedException` or handling the exception, with business methods `processResult`, `recordTaskFailure`, and `recordCancellation`. Core point: distinguish **`TaskRejectedException` at `submit()`** from **`ExecutionException` at `get()`**, and **`TimeoutException` when the caller waits too long**. Never pick timeouts or retries arbitrarily: control already-executed side effects and ensure idempotency.

| Symptom | Where it happens | Action to consider |
| --- | --- | --- |
| `TaskRejectedException` | `submit` / task submission | Shed load, return backpressure, durable queue, record rejection; usually no Future exists |
| `ExecutionException` | `Future.get()` | Inspect `getCause()`, classify error, bounded retry if idempotent |
| `InterruptedException` | Caller thread waiting in `get()` | Restore interrupt flag and cancel/exit per caller contract |
| `TimeoutException` | `get(timeout)` | Evaluate timeout, return partial/fallback result, optionally request cancel; task may still be running |
| `CancellationException` | `get()` on a cancelled Future | Distinguish deliberate cancellation from processing error |
| `isDone() == true` | Status check | Only says "finished"; call `get()` to learn success/failure |

**Operational note:** `Future.get()` blocks **the calling thread** rather than offloading waiting to Spring. Calling `get()` right after `submit()` inside an HTTP handler uses the executor to run the task while still holding the request thread waiting; sometimes that is appropriate, but it is not an end-to-end non-blocking asynchronous pipeline.

## 6. Cancellation and Interrupts Have Limited Semantics

`future.cancel(false)` tries to cancel work that has not started or marks cancellation without requesting an interrupt on a running thread. `future.cancel(true)` may send an interrupt to the worker. Both are control requests on the **Future/task**, not a transaction rollback or "undo".

A task that responds properly to interrupts:

~~~java
Future<?> task = executor.submit(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            performOneBoundedUnitOfWork();
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    } finally {
        releaseResources();
    }
});

// When business logic explicitly decides to stop:
task.cancel(true);
~~~

This snippet illustrates a **lifecycle control pattern**, where `performOneBoundedUnitOfWork()` and `releaseResources()` belong to application code. The example assumes a unit of work can throw `InterruptedException`, finishes within bounded time, and is safe to retry. If an underlying API does not respond to interrupts, the task can keep running even though the Future is in cancelled state. Separate timeouts for HTTP/database calls and strategies for partial side effects are still needed.

**Never use `isDone()` or `cancel(true)` as confirmation that a DB write, sent email, or payment has been undone.** For critical operations, final state must be persisted and verified in the system owning the data.

## 7. submitCompletable(): Option for Non-Blocking Processing Chains

Spring Framework 6.0+ adds:

~~~java
CompletableFuture<Integer> total = executor.submitCompletable(() -> {
    return expensiveCalculation();
});

CompletableFuture<String> display =
    total.thenApply(value -> "total=" + value)
         .exceptionally(error -> "unavailable");

display.thenAccept(System.out::println);
~~~

The snippet above is **illustrative integration code**, assuming `executor` and `expensiveCalculation()` already exist. `CompletableFuture` allows chaining `thenApply`, `thenCompose`, `whenComplete`, `exceptionally`, and coordinating multiple tasks without requiring the caller to call `get()` immediately. `submitCompletable(Runnable)` returns `CompletableFuture<Void>`, completing normally with `null`.

However, **continuations also need to choose where they run**:

- `thenApply(...)` without the `Async` suffix may run on the thread completing the future or the thread invoking the method, depending on completion state.
- `thenApplyAsync(...)` without an executor argument uses `CompletableFuture`'s default asynchronous facility (typically `ForkJoinPool.commonPool()`), not automatically returning to the Spring pool used earlier.
- If you want to control resources, use `thenApplyAsync(function, executor)` with the `AsyncTaskExecutor` you own and bound.
- `join()` is also a blocking call if incomplete; failures are wrapped in `CompletionException`. `get()` uses `ExecutionException`. Using `CompletableFuture` does not automatically provide timeouts, idempotency, or transaction context.

`submitCompletable` expresses pipelines better than plain `Future`; when you only need to await a single task, `submit(Runnable/Callable)` remains a solid choice.

## 8. Choosing an AsyncTaskExecutor Implementation

| Implementation | Characteristics | Things to watch |
| --- | --- | --- |
| `ThreadPoolTaskExecutor` | Spring-style adapter for `ThreadPoolExecutor`; has core/max pool size, queue capacity, thread prefix, metrics such as active count/queue size | Must choose bounds and rejection policy; bean lifecycle and shutdown vary with configuration |
| `SimpleAsyncTaskExecutor` | Creates a new thread per task, **does not reuse threads like a pool**; can limit concurrency | Do not use as an unbounded pool; on JDK 21+ can enable virtual threads via configuration |
| `ConcurrentTaskExecutor` | Adapter for an existing `java.util.concurrent.Executor` | Scheduling/queue/rejection behavior comes from the delegate executor; choose adapter when you already have a custom executor |
| `TaskExecutorAdapter` | Spring adapter for a raw JDK executor | Must understand resource ownership, exception translation, and delegate semantics |
| `SyncTaskExecutor` | Executes directly on caller thread | **Only implements `TaskExecutor`**, does not satisfy the async contract of `AsyncTaskExecutor` |

Example of configuring a bounded pool via Spring:

~~~java
@Bean("ioExecutor")
ThreadPoolTaskExecutor ioExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(100);
    pool.setThreadNamePrefix("io-");
    pool.setRejectedExecutionHandler(
        new java.util.concurrent.ThreadPoolExecutor.AbortPolicy()
    );
    return pool;
}
~~~

This is an **illustrative `@Bean` snippet** that must live inside a `@Configuration` class with the corresponding Spring imports. The numbers 4/8/100 are illustrative only, not right for every system. With `ThreadPoolTaskExecutor`, a queue with positive capacity normally causes tasks to queue before growing workers beyond `corePoolSize`; expansion up to `maxPoolSize` happens only once the queue is full. Thus raising `maxPoolSize` while keeping a very large queue may fail to increase concurrency as expected.

Note that `ThreadPoolTaskExecutor` defaults to core size 1 and a very large queue capacity; **do not** leave those defaults in production without load testing. When both pool and queue run out of capacity, tasks may be rejected. If using caller-runs instead of abort, `submit` latency can grow and the caller must absorb backpressure.

## 9. Picking the Right Abstraction: Manual submit, @Async, ExecutorService

| Scenario | Recommended choice |
| --- | --- |
| Need to explicitly submit a `Runnable` and receive a `Future` to wait/cancel | Inject `AsyncTaskExecutor` and call `submit(Runnable)` |
| Task returns `T` | `submit(Callable<T>)` |
| Need multi-stage processing / composing futures | `submitCompletable(...)` and continuations with an explicit executor |
| Want bean method calls intercepted for async execution | `@EnableAsync` + `@Async`, invoked through the Spring proxy |
| Need `invokeAll`, `invokeAny`, or direct shutdown on a raw Java pool | Own/inject `ExecutorService` per JDK contract; do not force Spring interfaces to supply APIs they lack |
| Only need fire-and-forget execution with separate error monitoring | `execute(Runnable)` may suffice, though no Future is returned |

**Manual `submit` does not require a Spring proxy:** a service can call `executor.submit(...)` even inside the same instance; it is a direct executor API. By contrast, `@Async` relies on an interceptor in default proxy mode; `this.someAsyncMethod()` normally bypasses the proxy and is not dispatched asynchronously.

**Do not equate a manual submit's `Future` with an `@Async` method's return type.** With `@Async`, the proxy dispatches the call and returns a future to the caller; return-type rules, propagation, and error handling follow the annotation's documentation. This lesson focuses on `AsyncTaskExecutor.submit`.

## 10. Responsibilities That submit Does Not Handle Automatically

### 10.1. Thread Safety and Input Data

Two concurrent tasks can hold references to the same collection, entity, or singleton bean. `submit` does not copy or freeze input data and does not make a `HashMap` thread-safe. Prefer immutable commands, local variables, proper concurrent structures, and clearly scoped synchronization.

### 10.2. ThreadLocal, Security, and Logging

The caller often carries context such as MDC, request attributes, principal, and transaction resources. The executor thread is not automatically guaranteed to inherit all of these contexts; when needed, choose `TaskDecorator` or appropriate security-aware/context-propagation adapters and clean up context in `finally`. Do not pass a live request object to a task that outlives the request.

**Subtlety with TaskDecorator:** on `ThreadPoolTaskExecutor.submit` calls, the wrapped runnable received by the decorator may be a `FutureTask` that already catches exceptions from the underlying work. A `try/catch` around `runnable.run()` inside the decorator may not see business errors; inspect `Future.get()` or design another result-observation mechanism.

### 10.3. Transaction and Request Boundaries

In imperative applications, Spring transactions are normally bound to the current thread. Submitting work via `submit` **does not transfer the caller's transaction to the worker thread**. If the task needs database writes, start an appropriate transaction on the worker itself, such as calling a `@Transactional` service bean through a Spring proxy or using `TransactionTemplate`. The worker may run before the caller's transaction commits, so a task must not read uncommitted writes or emit external events under the assumption that commit has already succeeded.

### 10.4. Reliability and Idempotency

`submit` places tasks into an executor inside a **live process**. If the JVM is killed after acceptance but before completion, `Future` is not a durable job record. When business rules require surviving restarts or preventing duplicates, persist commands/events in a database or durable queue, and design idempotency keys, retry/backoff, and completion states.

## 11. Common Mistakes and Fixes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| "`submit` returned a Future, so the task definitely succeeded" | The Future may still be waiting, failed, or cancelled | Observe `get`, callbacks/completion, or metrics |
| "`future.isDone()` is true means it succeeded" | Exceptions and cancellation also complete a Future | Check for failure/cancellation before treating as success |
| Calling `get()` right after each `submit` in a loop | Accidentally serializes waiting and loses concurrency | Submit tasks first, collect Futures, then await/aggregate with deadlines |
| Discarding the `Future` returned by `submit` unobserved | Exceptions inside the Future can go silent | Ensure an owner observes results/failures |
| Calling `future.get(1, SECONDS)` and assuming timeout stopped the task | Timeout only limits how long the caller waits | Apply explicit cancellation policy and I/O-level deadlines |
| Using `cancel(true)` as a rollback | Interrupts do not undo side effects that already happened | Use transactions/compensation, idempotency, checkpoints |
| Catching only `ExecutionException` around `submit` | Rejection happens at submission time, not inside the Future | Catch `TaskRejectedException` around `submit` |
| Mixing up `AsyncTaskExecutor` and `ExecutorService` | They do not share the same full API | Choose the interface that fits your needs |
| Expecting `@Async`/transaction/request context to transfer automatically | Thread and proxy boundaries are separate | Use explicit context propagation and separate transactions |
| Using an unbounded pool/queue to "avoid rejections" | Increases latency/memory usage and risks OOM | Bounded queue, rejection policy, backpressure, and metrics |

## 12. How to Test a submit() Path

1. **States:** verify `submit(Runnable)` resolves to `null`, `submit(Callable<T>)` yields the expected `T`, and `Future.get()` waits for completion.
2. **Exceptions:** submit a task that throws a known exception; assert `get()` throws `ExecutionException` with the expected `getCause()` type. Avoid tests relying only on worker logs.
3. **Timeout/cancel:** use a `CountDownLatch`/barrier to hold a pending task, then test `get(timeout)`, `cancel(true)`, and `isCancelled`; avoid fixed `Thread.sleep` delays.
4. **Rejection:** configure a small pool and queue, block the worker with a latch, submit beyond capacity; assert the rejection policy and the caller's handling path.
5. **Concurrency:** measure concurrent threads, verify load bounds, and test shared mutable state in beans.
6. **Lifecycle:** close the ApplicationContext while tasks are running/pending; verify the shutdown policy and that critical business data is not lost.
7. **Observability:** log valid taskId/correlationId; monitor queue depth, active count, task duration, failures/rejections, and timeouts.

## 13. Correct-Usage Checklist

- I know whether the `executor` variable is genuinely `AsyncTaskExecutor` or only `TaskExecutor`.
- I choose `Runnable` when no return value is needed, and `Callable<T>` when a result is required.
- I distinguish `submit` acceptance, `Future` completion, and business success.
- I have a clear owner responsible for observing `Future` and handling task exceptions.
- I separate rejection errors at **submit** from execution failures at **get**.
- I handle interrupts, timeouts, and cancellation without assuming automatic rollback.
- I configure executor bounds, queue capacity, overload/rejection, and shutdown for real load.
- I do not expect transaction, request, or security context to propagate automatically to workers.
- I use a durable queue/outbox/idempotency if work must recover after process termination.

**Conclusion:** `AsyncTaskExecutor` extends Spring's task execution capability so callers receive a **`Future` to observe asynchronous results**. `submit(Runnable)` tracks completion with a `null` result; `submit(Callable<T>)` returns a value of type `T`. System correctness still depends on executor configuration, error policies, state/transaction boundaries, and business design.

## References

- Spring Framework Javadoc – AsyncTaskExecutor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html
- Spring Framework Javadoc – TaskExecutor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework Javadoc – ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference – Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Java SE 17 Javadoc – Future: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 Javadoc – ExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html