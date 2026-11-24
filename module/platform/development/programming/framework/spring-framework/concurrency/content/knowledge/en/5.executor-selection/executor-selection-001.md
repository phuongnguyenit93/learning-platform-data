# SyncTaskExecutor Runs Immediately on the Calling Thread

## 1. Goal and Core Idea

In Spring Framework, `TaskExecutor` is an abstraction for submitting work (a `Runnable`) to an execution component. The name “executor” **does not guarantee** that the work will be dispatched to a new thread. `org.springframework.core.task.SyncTaskExecutor` is the clearest example: when `execute(task)` is called, it **runs `task.run()` directly on the calling thread**, and only returns after `run()` finishes or throws an exception.

This is a deliberate choice in the “**Executor Selection**” group: use it when you want synchronous execution, predictable behavior, or do not need to decouple the task from the caller. Do not use it merely because you see the word “TaskExecutor” and assume the work will automatically run in the background.

For example, an HTTP thread handling a request:

~~~text
Thread http-nio-8080-exec-1:
  log("before")
  syncTaskExecutor.execute(job)
    -> job.run()        [still the same http-nio-8080-exec-1]
    -> job.run() finishes
  log("after")

The order is always before -> entire job -> after if the job completes normally.
~~~

**Important distinction:** “synchronous” here means **each `execute` call waits for its own task**. It does **not** mean that all tasks across the entire application are serialized by a lock. If request A and request B are being processed on two different HTTP threads, the same `SyncTaskExecutor` instance can run two tasks concurrently on those two calling threads.

## 2. Execution Mechanism

The simplest contract is:

~~~java
// Pseudocode illustrating the mechanism; not verbatim Spring source code.
public void execute(Runnable task) {
    task.run(); // Invoked directly on the current thread.
}
~~~

The actual Spring version also validates arguments and may add mechanisms depending on the framework version; however, the defining property of `SyncTaskExecutor` remains **execution on the caller thread**. With Spring Framework 6.x used in the example below, there is no thread pool or task queue inside this executor.

### Direct Consequences

- **No thread switching:** `Thread.currentThread()` inside the task is the same thread object as the caller at the time of invocation.
- **Blocks the caller:** if the task takes 2 seconds, the `execute` call must also remain in the task for about 2 seconds, plus the small overhead of the Java call. If the caller is an HTTP request thread, response time is prolonged.
- **No separate queue:** there is nowhere to submit work and return immediately, and no fixed number of workers or throughput independent of the number of calling threads.
- **Direct result / error:** `execute(Runnable)` returns `void`; return values must be managed by the caller/task code. If `Runnable.run()` itself throws an unchecked exception without catching it, the exception propagates out of the `execute` call when used directly.
- **Preserves thread context:** thread-local state, the thread context classloader, and the current thread's transaction association remain in the same context while the task runs. This can be convenient in tests, but the task can also inadvertently modify the caller's context.
- **Does not automatically protect shared state:** two independent caller threads can still concurrently modify the same field of a singleton service; atomics/locks/transactions are still needed according to the proper data scope.

Unlike `ThreadPoolTaskExecutor`, there is no `corePoolSize`, `maxPoolSize`, or `queueCapacity` configuration following the thread-pool model for this executor in Spring 6.x. Do not infer properties from other Spring versions for the chosen API.

## 3. Runnable Example: Using SyncTaskExecutor Directly

This example uses **Java 17** and **Spring Framework 6.2.12**. It demonstrates three points with deterministic output:

1. The task runs between the `before/after` lines on the exact caller thread.
2. An unchecked exception from the task propagates to the caller when calling `execute` directly.
3. Two different calling threads can run tasks concurrently on one `SyncTaskExecutor` (there is no global serialization lock).

### 3.1. File Structure

~~~text
sync-executor-demo/
├── pom.xml
└── src/main/java/com/example/executor/
    └── SyncTaskExecutorDemo.java
~~~

### 3.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>sync-executor-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` transitively brings in `spring-core`, which contains `TaskExecutor` and `SyncTaskExecutor`. Neither Spring Boot, a web server, nor annotations are needed to call the API directly.

### 3.3. SyncTaskExecutorDemo.java

~~~java
package com.example.executor;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;

public final class SyncTaskExecutorDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        Thread.currentThread().setName("request-caller");
        TaskExecutor executor = new SyncTaskExecutor();

        REQUEST_ID.set("REQ-42");
        try {
            System.out.println("1 before: " + Thread.currentThread().getName());

            executor.execute(() -> {
                System.out.println("2 task: " + Thread.currentThread().getName());
                System.out.println("3 trace: " + REQUEST_ID.get());
            });

            System.out.println("4 after: " + Thread.currentThread().getName());
        } finally {
            REQUEST_ID.remove();
        }

        try {
            executor.execute(() -> {
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException ex) {
            System.out.println("5 caught: " + ex.getMessage());
        }

        demonstrateMultipleCallers(executor);
    }

    private static void demonstrateMultipleCallers(TaskExecutor executor)
            throws InterruptedException {
        CountDownLatch bothEntered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxActive = new AtomicInteger();

        Runnable job = () -> {
            int now = active.incrementAndGet();
            maxActive.accumulateAndGet(now, Math::max);
            bothEntered.countDown();

            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        };

        Thread callerA = new Thread(() -> executor.execute(job), "caller-A");
        Thread callerB = new Thread(() -> executor.execute(job), "caller-B");

        callerA.start();
        callerB.start();

        // Both have entered the task and are waiting on release; there must be 2 active tasks.
        bothEntered.await();
        release.countDown();
        callerA.join();
        callerB.join();

        System.out.println("6 max-active: " + maxActive.get());
    }
}
~~~

### 3.4. Run Command and Stdout

In the `sync-executor-demo` directory, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.executor.SyncTaskExecutorDemo
~~~

The lines **printed by the program**, in exact order:

~~~text
1 before: request-caller
2 task: request-caller
3 trace: REQ-42
4 after: request-caller
5 caught: boom
6 max-active: 2
~~~

Because `execute` runs the task directly, line 4 cannot appear before line 2 or 3 when the task succeeds. `REQUEST_ID` uses `ThreadLocal`, so the task sees the same `REQ-42` value on the caller thread. The final part uses two `CountDownLatch` instances to ensure both task A and task B have entered `run()` before releasing them; `max-active: 2` proves that the same executor can have **two tasks running simultaneously** when two different caller threads call it concurrently. This value is measured with `AtomicInteger`; the example intentionally uses JDK synchronization primitives to avoid timing-dependent test flakiness.

The `ThreadLocal.remove()` call in `finally` is necessary if the calling thread is later reused, such as a servlet container thread. The code above is a standalone Java file inside the Maven project just shown; it does not depend on any external files.

## 4. Using SyncTaskExecutor in a Spring Bean and @Async

In a Spring application, you can register this executor as a bean and inject it via the common `TaskExecutor` type. Only choose `@Async("syncExecutor")` when you **intentionally want calls through the proxy to execute synchronously** (commonly for testing). The `@Async` annotation on a method **cannot force the creation of a new thread** if the selected executor is `SyncTaskExecutor`.

To verify both wiring and the Spring AOP proxy mechanism, add a second file to the same Maven project from section 3:

`src/main/java/com/example/executor/AsyncSyncExecutorDemo.java`

~~~java
package com.example.executor;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncSyncExecutorDemo {
    @Bean("syncExecutor")
    public TaskExecutor syncExecutor() {
        return new SyncTaskExecutor();
    }

    @Bean
    public ReportTask reportTask() {
        return new ReportTask();
    }

    public static void main(String[] args) {
        Thread.currentThread().setName("request-caller");

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncSyncExecutorDemo.class)) {
            // Retrieve the Spring-managed bean: the call goes through the @Async proxy.
            ReportTask worker = context.getBean(ReportTask.class);

            System.out.println("A before");
            worker.generate();
            System.out.println("C after");
        }
    }

    public static class ReportTask {
        @Async("syncExecutor")
        public void generate() {
            System.out.println("B task: " + Thread.currentThread().getName());
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.executor.AsyncSyncExecutorDemo
~~~

Lines printed by the program (excluding any framework logs if present):

~~~text
A before
B task: request-caller
C after
~~~

`@EnableAsync` enables proxy support for `@Async`; `@Async("syncExecutor")` selects the exact executor by bean name. Because the executor runs synchronously, `worker.generate()` only returns after the method body finishes. In this example, `ReportTask` is a non-final public nested class with a public method; Spring can create a proxy for the bean. If you call `this.generate()` from inside `ReportTask` itself, the internal call normally bypasses the `@Async` proxy in proxy mode; in that case the method also runs directly, but **because it bypassed the interceptor**, not because the executor was applied. Distinguish these two causes to diagnose issues accurately.

### Why Shouldn't You Infer All @Async Behavior from execute?

- With a **direct** `syncExecutor.execute(runnable)` call, an unchecked exception from `Runnable.run()` normally propagates directly to the caller (as in example 3).
- When going through an **`@Async` proxy**, Spring wraps the task and handles results/exceptions according to the return type. For `void`, uncaught errors are passed to the `AsyncUncaughtExceptionHandler` mechanism; for `Future/CompletableFuture`, the caller can observe errors through the future result (such as `get()/join()`). Do not promise that every exception from an `@Async` method will be thrown just like a direct `execute` call.
- When the task runs synchronously, a `CompletableFuture` completed during task submission may already be done by the time the calling method returns. An API named “async” and a `Future` return type **do not guarantee** that the operation actually ran in the background.
- `@Async` supports a limited set of return types and follows Spring's proxy rules; those details do not change the synchronous nature of `SyncTaskExecutor`.

Example with Java `CompletableFuture` (illustrative snippet inside a method, assuming `executor` is the `TaskExecutor` from section 3):

~~~java
CompletableFuture<Void> future = CompletableFuture.runAsync(
        () -> System.out.println("runs inline"), executor);
System.out.println(future.isDone()); // true when the task succeeded and has finished running
~~~

`CompletableFuture.runAsync` accepts an `Executor`, which calls `executor.execute`; with `SyncTaskExecutor`, the task executes immediately, so `future` is already complete when `runAsync` returns. If the task fails, `CompletableFuture` stores the error to be observed via `join/get`; that is the behavior of the `CompletableFuture` wrapper and does not contradict the direct `execute` mechanism.

## 5. Impact on HTTP Requests, Transactions, and Thread Context

Suppose a controller calls:

~~~java
// Illustrative snippet inside a @RestController; not a complete class.
@GetMapping("/reports/{id}/refresh")
public String refresh(@PathVariable String id) {
    syncExecutor.execute(() -> reportService.refresh(id));
    return "Accepted";
}
~~~

If `reportService.refresh(id)` makes a 5-second DB call, the HTTP request must wait about 5 seconds before returning the word “Accepted”. Using the word “Accepted” in the response body **does not** turn the task into background processing; an HTTP `202 Accepted` status is also inappropriate if the task has actually already finished during the call with no further deferred processing. For synchronous operations, the API should return an HTTP code/body reflecting the processed result; for genuinely long-running background tasks, use a bounded asynchronous executor or a message queue, along with a job ID to poll status.

### Which Context Remains on the Thread?

When using `SyncTaskExecutor` directly:

- `ThreadLocal` values set by the caller remain present in the task, including many logging MDC configurations, security contexts, or other thread-bound contexts.
- `TransactionSynchronizationManager` records the transaction association on the current thread. Because the task runs on the same thread, if a transaction is already active, accessing resources via transaction-bound context may participate in that same transaction, depending on the service methods and propagation rules.
- `RequestContextHolder` typically holds request attributes during a synchronous HTTP request; a direct task can see them while the context is active. This **does not** mean you can retain and use the request context after the request finishes.
- If the task modifies MDC, security context, `ThreadLocal`, or the context classloader without restoring them, the caller can observe those changes right after `execute`. Clean up or restore them in `finally` according to ownership.

Do not infer that `SyncTaskExecutor` *creates transactions on its own*, automatically propagates them to other threads, or replaces `@Transactional`. If the code calls through the Spring proxy of a `@Transactional` service, normal transaction rules still apply; if self-invocation bypasses the proxy, the annotation may not be processed.

### Why Does This Matter When Changing Executors?

A configuration change from `SyncTaskExecutor` to `ThreadPoolTaskExecutor` can expose false assumptions:

1. The caller returns before the task finishes processing; data read immediately after `execute` may not be ready yet.
2. The task runs on a worker thread, so the caller's `ThreadLocal` and transaction association **do not automatically** follow it. Pass required data explicitly, such as request ID, authenticated user ID, or an immutable DTO; use an appropriate context propagation mechanism if genuinely needed.
3. Worker exceptions cannot implicitly be caught with a `try/catch` around the task submission call; you need a `Future`, error handler, callback, or job status.
4. A mutable collection that was only safe because the task previously ran inline can develop a race condition if the caller keeps modifying it while the worker reads it. Pass an immutable snapshot or apply proper synchronization.

Conversely, when tests use `SyncTaskExecutor`, running on the same thread can mask race/visibility bugs and missing context propagation issues that will surface on the production executor. Add tests that run on a realistic executor whenever those properties are system requirements.

## 6. Comparison When Selecting an Executor

| Option | Where does it run? | Does `execute` wait for the task? | Strengths / when to use |
| --- | --- | --- | --- |
| `SyncTaskExecutor` | On the caller thread | **Yes**, until the task finishes | Synchronous unit/integration tests, simple execution flows |
| `SimpleAsyncTaskExecutor` | Creates a thread per task by default; no pool-style reuse | Usually returns after handing off the task; may wait if a limit is configured | Short/specialized independent tasks; must understand thread-creation cost and limits |
| `ThreadPoolTaskExecutor` | Workers in a pool, optionally with a queue | Usually returns after handing off; may reject when full | Controlled background load, decoupled from requests; configure pool/queue/rejection |
| `ThreadPoolTaskScheduler` | Executor combined with periodic scheduling | Invoked on schedule rather than directly by a caller | `@Scheduled` and fixed/cron triggers |
| `ThreadPoolExecutor.CallerRunsPolicy` (JDK) | Runs on the caller only when the pool rejects a task | Only in the corresponding fallback situation | Backpressure when the queue is saturated; **different** from an always-synchronous executor |

`TaskExecutor` is an interface; it does not promise a new thread. `SyncTaskExecutor` is **not** the same as a “single-thread executor”: a single-thread executor normally has **one dedicated worker thread** and queues tasks; `SyncTaskExecutor` uses **whichever caller thread** calls `execute`.

Specifically, when handling 2 concurrent requests:

~~~text
Request A (thread-A) ---> sync.execute(taskA) ---> taskA.run() on thread-A
Request B (thread-B) ---> sync.execute(taskB) ---> taskB.run() on thread-B

Two tasks can execute overlapping in time.
There is no shared worker or shared mutex in SyncTaskExecutor.
~~~

If the goal is to allow only one task at a time across the entire JVM, you need a true single-worker executor or an appropriate lock. If the goal is one task at a time **across multiple pods**, you must use a coordination/lock mechanism in a shared store, not `SyncTaskExecutor`.

### Choosing an Executor for a Long-Running Report Task

For a report-generation request involving slow DB reads and PDF rendering, `SyncTaskExecutor` causes the request to hold the HTTP thread. Choosing a genuinely asynchronous bounded executor is more reasonable, such as this illustrative bean in a Spring application:

~~~java
// Illustrative snippet inside a @Configuration class.
@Bean("reportExecutor")
public ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(20);
    pool.setThreadNamePrefix("report-");
    pool.setWaitForTasksToCompleteOnShutdown(true);
    return pool;
}
~~~

In the code above, you need to import `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` and `org.springframework.context.annotation.Bean`. Spring manages the bean lifecycle when registered in the context; if you instantiate `new ThreadPoolTaskExecutor()` manually outside Spring, you must call `initialize()` before using it and shut down resources properly. When the queue/pool is full, choose an appropriate rejection policy and HTTP response instead of accepting work unboundedly. Moving tasks to a pool does not by itself make work durable across restarts; critical reports should store job state in a DB or durable queue.

## 7. When Should and Shouldn't You Use SyncTaskExecutor?

**Consider using it when:**

1. **Tests need determinism:** inject `TaskExecutor` via the constructor and pass `SyncTaskExecutor` in unit tests so assertions run right after `execute` and observe results immediately without waiting or polling. For real concurrency tests, replace it with an appropriate pool.
2. **Small, intentionally synchronous operations:** when the `TaskExecutor` abstraction is shared, yet one branch requires synchronous behavior without needing to decouple the request from the task.
3. **Debugging the application:** temporarily switching to the synchronous executor in a test environment keeps the call stack continuous. Keep in mind that timing and race conditions in production may differ.

**Not suitable when:**

- Generating PDFs, sending emails, calling slow APIs, or processing thousands of records when the endpoint needs to respond immediately.
- Wanting to cap the total number of concurrent tasks using the executor itself in version 6.x: the number of active tasks can equal the number of concurrent callers.
- Wanting JVM-wide sequential execution, scheduled runs, retries across restarts, or load distribution across multiple nodes.
- Wanting to verify data synchronization bugs between worker threads while the test runs everything inline.

### Usage in Tests

Suppose a service receives the abstraction through its constructor:

~~~java
// Illustrative snippet; the class also needs to import TaskExecutor.
public final class RefreshCoordinator {
    private final TaskExecutor executor;
    private boolean finished;

    public RefreshCoordinator(TaskExecutor executor) {
        this.executor = executor;
    }

    public void refresh() {
        executor.execute(() -> finished = true);
    }

    public boolean isFinished() {
        return finished;
    }
}
~~~

In a test running sequentially on the same thread:

~~~java
RefreshCoordinator coordinator =
        new RefreshCoordinator(new SyncTaskExecutor());
coordinator.refresh();
assert coordinator.isFinished();
~~~

This is an *illustrative test snippet*, not two standalone Java files. If run with Java `assert`, `-ea` must be enabled; in JUnit, `assertTrue(...)` should be used. The `finished` field is not synchronized for a production async executor; precisely because the test uses the sync executor, visibility issues can be missed. For production async support, use `CompletableFuture`, `CountDownLatch`, or a thread-safe state variable suited to the design rather than relying on a plain boolean field.

## 8. Common Mistakes and How to Diagnose Them

| Symptom / assumption | Actual cause | Check or fix |
| --- | --- | --- |
| “`@Async` still runs on the HTTP thread” | The selected bean is `SyncTaskExecutor`; or self-invocation bypassed the proxy | Print the thread name, check the executor name in `@Async` and the call path through the proxy |
| “`execute` returns slowly” | The task runs inline, so the caller waits for it | Measure time right before/after; switch to a pool if real background execution is needed |
| “With `SyncTaskExecutor`, there can't be any race conditions” | Multiple caller threads still run tasks in parallel | Use latches in tests, and locks/atomics/transactions for shared state |
| “Catching errors around `execute` doesn't catch `@Async` errors” | The proxy / `Future` has its own error-handling path | Check the return type, `AsyncUncaughtExceptionHandler`, and `Future.get/join` |
| “Transaction/request context exists in tests but not in production” | Tests use the same thread, while production uses a worker thread | Pass data explicitly, and open a transaction inside the worker when needed |
| “A single-thread executor and SyncTaskExecutor are the same” | A single-thread executor has a worker and queue; Sync uses the caller | Inspect the thread name and the before/after call order |
| “Tests pass with sync executor so production is fine” | Tests do not simulate concurrent scheduling, queues, shutdown, or rejection | Add integration/load tests with the production configuration |

### Pre-Selection Checklist

- Does the API need to return immediately after *submitting* the work? If yes, `SyncTaskExecutor` does not meet the background-processing goal.
- How long can the work take? Will each task hold a request thread or an event-loop thread? On an event-loop/reactive stack, strictly avoid running blocking work with a synchronous executor and expecting it not to block the event loop.
- Does the task use a transaction, MDC, `SecurityContext`, or thread-bound request data? If moving to a worker, manage propagation and ownership.
- Are there requirements for capping concurrent tasks, queuing, timeouts, cancellation, graceful shutdown, or recovery after restart? If yes, a simple inline executor is insufficient.
- Is the test trying to verify sequential logic or real concurrency behavior? Choose the right executor for the testing goal.

## 9. Self-Check Questions

1. If `execute` is called on `http-nio-8080-exec-2`, what is `Thread.currentThread().getName()` inside `Runnable`? When does the statement after `execute` run?
2. Can two HTTP threads calling the same `SyncTaskExecutor` run two tasks concurrently? Why doesn't the name “sync” mean system-wide serial execution?
3. In direct `execute`, where does an `IllegalStateException` thrown by `Runnable` go? How does this differ when the method runs through an `@Async` proxy or when using `CompletableFuture`?
4. Why is `ThreadLocal` visible inside the task, and why must `ThreadLocal` still be cleared in `finally`?
5. If tests inject `SyncTaskExecutor` while production injects `ThreadPoolTaskExecutor`, which assumptions about results, transactions, shared variables, or errors might need to be redesigned?
6. When an endpoint must accept a report-rendering request and immediately return 202, which executor and state-storage mechanism would you choose?

**Key takeaway:** `SyncTaskExecutor` provides the `TaskExecutor` abstraction while actually running `Runnable.run()` **directly on the caller thread**. It is useful for intentionally synchronous processing and deterministic tests, while it can block the caller; it is not a thread pool, a queue, or an application-wide synchronization mechanism.

Official documentation: [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) and [Spring Framework 6.2 — SyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/SyncTaskExecutor.html).