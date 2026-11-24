# execute(Runnable) Does Not Implicitly Guarantee Running on Another Thread

> **Topic:** Spring Framework – Concurrency / TaskExecutor  
> **Key Idea:** `TaskExecutor.execute(Runnable)` is a request to execute a task according to the executor's strategy. Looking at an `execute(...)` call alone, **you cannot conclude** that the task will run on another thread, you cannot conclude that it always returns immediately, and you cannot conclude that the task has finished when the method returns.

## Learning Objectives

After this lesson, you will be able to:

1. Read the contract of `java.util.concurrent.Executor` and `org.springframework.core.task.TaskExecutor` accurately.
2. Explain why `SyncTaskExecutor` executes immediately on the **calling thread**, whereas `SimpleAsyncTaskExecutor` and `ThreadPoolTaskExecutor` normally hand work off to another thread.
3. Point out the situation where `CallerRunsPolicy` causes a thread pool to run a task directly on the calling thread even though the pool normally has workers.
4. Distinguish **submitting a task**, **starting a task**, **completing a task**, **running asynchronously**, and **running on another thread**.
5. Write Java 17 examples and reliable tests using `Thread` identity and `CountDownLatch`, instead of guessing from logs or `Thread.sleep(...)`.
6. Choose appropriate executor configuration, rejection handling, and thread-context management in a Spring application.

## 1. What Does `execute(Runnable)` Actually Promise?

In Java, the `Executor` interface has one basic method:

~~~java
public interface Executor {
    void execute(Runnable command);
}
~~~

In Spring, `TaskExecutor` extends `Executor` and likewise provides `execute(Runnable task)`. Both interfaces separate **the code that creates the work** from **how the work is run**. The caller hands a `Runnable` to the executor; the executor's implementation and configuration decide where and when it runs.

Therefore:

- `execute` **does not mean** `new Thread(task).start()`.
- An implementation may call `task.run()` directly on the same call stack, so the task finishes **before `execute` returns**.
- Another implementation may place `task` into a queue for a worker to run later; the task may also start **before `execute` returns**.
- Implementations may use a new thread, an existing worker, or delegate to another executor. Not every `TaskExecutor` is a thread pool.
- A task may be rejected when capacity is exhausted or the executor has shut down. Depending on the rejection policy, the call may throw an error, run on the caller itself, or drop the task. Therefore, seeing `execute` return does not mean the task definitely completed.

Spring's Javadoc for `TaskExecutor` explicitly states that execution strategies may be **synchronous** or **asynchronous**. `execute` returns `void`: it provides neither a result nor a handle to await completion. If you need result or failure feedback, choose an API returning `Future`/`CompletableFuture` and manage the corresponding executor contract.

### Do Not Conflate Three Questions

| Question | Meaning | Can it be inferred from `execute(Runnable)` alone? |
| --- | --- | --- |
| Does the task run on the **same thread** or **another thread**? | Thread identity | **No** |
| Does the `execute` call **return quickly**? | Caller latency | **No** |
| When `execute` returns, has the task **completed**? | Completion status | **No** |

For example, `SyncTaskExecutor` answers all three in a predictable way: **same thread**, the caller blocks while running the task, and the task has already finished before `execute` returns normally. A queued executor may hand work to a worker yet still block the caller while waiting for resources. Being "non-blocking" and "not running on the same thread" are two properties that must be evaluated separately.

## 2. Visualizing the Call Path

### Case A: Synchronous Execution Directly on the Caller

~~~text
Request/main thread
    |
    | calls executor.execute(task)
    |       |
    |       +-- task.run()
    |       |     does work / may throw exception
    |       +-- run() finishes
    |
    +-- execute() returns
    +-- next statement
~~~

This is `SyncTaskExecutor`: it invokes `Runnable.run()` directly. In this case, no new task-execution thread appears simply because you used the executor API.

### Case B: Handing Off Work to a Worker

~~~text
Request/main thread                 Worker thread
    |                                     |
    +-- execute(task)                     |
    |      +-- accept/enqueue ------------+-- take task
    +-- can continue                      +-- task.run()
    |                                     +-- complete
~~~

This is the usual strategy of `ThreadPoolTaskExecutor` when the pool accepts the task. When the worker starts, when the caller returns, and when the task completes **have no fixed global order** unless an explicit waiting/synchronization mechanism is used.

### Case C: Pool Full and Policy Falls Back to the Caller

~~~text
Request/main thread                 Thread pool
    |                                     |
    +-- execute(task)                     +-- all workers busy
    |      +-- queue full                  +-- queue full
    |      +-- CallerRunsPolicy
    |             +-- task.run()
    |             +-- complete
    +-- execute() returns
~~~

In this configuration, an executor that normally runs asynchronously can execute **a pool-rejected task directly on the calling thread**. This must be checked carefully when choosing an overload-protection policy.

## 3. Standalone Java SE 17 Example: Same API, Two Execution Modes

This section uses only Java SE to prove that the `Executor` contract allows multiple strategies. Create the file **`ExecutorDispatchDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorDispatchDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();

        // Valid: the implementation runs directly on the calling thread.
        Executor direct = Runnable::run;

        System.out.println("before direct");
        direct.execute(() -> System.out.println(
                "direct same thread = " + (Thread.currentThread() == caller)));
        System.out.println("after direct");

        // This ExecutorService creates a separate worker to process tasks.
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch completed = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                try {
                    System.out.println(
                            "pool same thread = " + (Thread.currentThread() == caller));
                } finally {
                    completed.countDown();
                }
            });

            completed.await(); // Wait for the task to finish printing; do not rely on sleep.
            System.out.println("after pool completed");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac ExecutorDispatchDemo.java
java ExecutorDispatchDemo
~~~

**Deterministic stdout:**

~~~text
before direct
direct same thread = true
after direct
pool same thread = false
after pool completed
~~~

Explanation:

- `Runnable::run` is a valid `Executor` implementation: given a `Runnable`, it calls `run()` immediately on the caller.
- `Executors.newSingleThreadExecutor()` uses a separate worker; comparing **`Thread` instances** returns `false`.
- `CountDownLatch.await()` preserves the ordering of the `after pool completed` line; it does not infer ordering from OS scheduling timing.
- `shutdown()` releases the executor after work completes. A program using a long-lived executor needs to manage its lifecycle or let the Spring container manage the bean.

This example proves the core point at the JDK level. Next, we apply it directly to Spring's `TaskExecutor`.

## 4. Spring Example: `SyncTaskExecutor` and `SimpleAsyncTaskExecutor`

### 4.1. Preparing a Small Runnable Project

Use **JDK 17+** and **Maven**. Create the structure:

~~~text
executor-spring-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── SpringTaskExecutorDemo.java
~~~

Contents of **`pom.xml`** (using Spring Core 6.2.16 so the example has a fixed version):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>executor-spring-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
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

Contents of **`src/main/java/SpringTaskExecutorDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

import org.springframework.core.task.SimpleAsyncTaskExecutor;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;

public class SpringTaskExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();

        TaskExecutor sync = new SyncTaskExecutor();

        System.out.println("before sync");
        sync.execute(() -> System.out.println(
                "sync same thread = " + (Thread.currentThread() == caller)));
        System.out.println("after sync");

        TaskExecutor async = new SimpleAsyncTaskExecutor("demo-worker-");
        CountDownLatch finished = new CountDownLatch(1);

        async.execute(() -> {
            try {
                System.out.println(
                        "async same thread = " + (Thread.currentThread() == caller));
            } finally {
                finished.countDown();
            }
        });

        finished.await();
        System.out.println("after async completed");
    }
}
~~~

Run inside the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SpringTaskExecutorDemo
~~~

**Program stdout** (any Maven logs are not part of the illustrated stdout):

~~~text
before sync
sync same thread = true
after sync
async same thread = false
after async completed
~~~

### 4.2. What Do We Learn from the Example?

- Both variables have the **same declared type** `TaskExecutor`; the difference lies in the actual implementation.
- `SyncTaskExecutor.execute` calls `run()` directly, so the executing thread is the caller. The `after sync` line only appears after the task finishes.
- `SimpleAsyncTaskExecutor` starts another thread for the task rather than pooling and reusing threads in the sense of `ThreadPoolTaskExecutor`. The example uses a latch to confirm the task printed before the program exited.
- Naming threads `demo-worker-...` helps observation during debugging, but does not replace comparing `Thread.currentThread() == caller`.
- `SimpleAsyncTaskExecutor` can apply concurrency limits and block when accepting additional work. Do not infer from the word `Async` that submission is always instantaneous or that unbounded resources are safe.

### 4.3. Distinguishing `TaskExecutor` and `AsyncTaskExecutor`

Spring has the subinterface `AsyncTaskExecutor` for executors with an asynchronous execution contract and support for task APIs returning handles. Its Javadoc states that `execute(Runnable)` is executed on another thread, unlike the general `TaskExecutor` contract.

When using a concrete executor, you must still inspect the **rejection-handling and adapter configuration**. For example, a thread pool's `CallerRunsPolicy` option intentionally shifts work back to the caller when the pool is saturated. Specific operational policies can break the assumption that "this task is always off-thread", even for objects implementing the async interface. If the application **must** run off the caller thread, pick an implementation/configuration that upholds that requirement and handle rejection transparently.

## 5. `ThreadPoolTaskExecutor`: Normally Dispatches to Workers, but Check Overload Policies

Spring's `ThreadPoolTaskExecutor` wraps configuring a JDK `ThreadPoolExecutor`. It normally assigns tasks to workers or a queue; a task does not equate to a new thread. Workers can be reused across many tasks, and tasks can wait in the queue.

In a Spring application with the `spring-context` dependency (or an appropriate Spring Boot starter), you can define an explicit configuration bean:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExecutorConfiguration {
    @Bean("applicationExecutor")
    ThreadPoolTaskExecutor applicationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-job-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor; // Spring manages initialize and shutdown for the bean.
    }
}
~~~

**This is a Spring application configuration snippet**, not a standalone runnable program. The Spring container initializes the bean before it is injected and used.

With `AbortPolicy`, when the pool rejects work, the call throws an exception instead of silently shifting the task onto the caller. In Spring, rejection through `TaskExecutor` is typically represented by `TaskRejectedException` (in the `RejectedExecutionException` family). The application must decide whether to retry, enqueue into a durable queue, return an overload error, or apply another business-appropriate mechanism.

### 5.1. Why Do Queue and Pool Sizes Affect Behavior?

Typical `ThreadPoolExecutor` rules:

1. If the current number of workers is below `corePoolSize`, a worker may be started to process the task.
2. Once enough core workers exist, the executor normally prefers placing work in the queue.
3. When the queue cannot accept more work, the executor may grow workers up to `maxPoolSize`.
4. When both workers and queue have reached their limits, the **rejection policy** decides the fate of the next task.

With a practically unbounded queue, `maxPoolSize` may have little chance to take effect; therefore, you must examine worker count, queue bounds, and processing speed together rather than looking only at the bean name.

### 5.2. `CallerRunsPolicy`: A Thread Pool Can Also Run Tasks on the Caller

If you configure:

~~~java
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.CallerRunsPolicy());
~~~

then when the pool is saturated **and has not shut down**, a task rejected from the pool runs directly on the thread calling `execute`. This is a form of **backpressure**: the caller is occupied doing the work itself, so the submission rate drops. Once the executor has shut down, `CallerRunsPolicy` may **drop** the task instead of running it. This policy must not be treated as a guarantee of successful dispatch in all situations.

Practical consequence: a controller or request-handling thread can take much longer because it unexpectedly has to execute the background task itself, causing latency spikes. For code that relies on separating transactions, security context, or thread-locals, shifting the task onto the caller can also alter observable behavior.

### 5.3. Standalone Java 17 Example Deterministically Triggering `CallerRunsPolicy`

The following file **`CallerRunsDemo.java`** deliberately keeps one worker busy, fills a queue of capacity 1, and then submits a third task. Because every condition is coordinated with latches, **the third task is guaranteed to go through the CallerRunsPolicy path** as long as the executor has not shut down.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();     // Worker is busy.
            pool.execute(() -> { });  // The single queue slot is full.

            // Pool is saturated: the policy will invoke run() directly on the caller.
            pool.execute(() -> System.out.println(
                    "third task same thread = " +
                    (Thread.currentThread() == caller)));
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("pool did not terminate");
        }
    }
}
~~~

Compile and run:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Exact output:

~~~text
third task same thread = true
~~~

**Why this test is reliable:** `workerStarted.await()` ensures the worker is holding the first task and waiting on `releaseWorker`; the second task enters the 1-slot queue; the third task has neither a free worker nor a free queue slot. `CallerRunsPolicy` executes that third task on the caller. No `Thread.sleep` is needed, and it does not depend on machine speed.

**Note:** This example tests the JDK `ThreadPoolExecutor` mechanism. With `ThreadPoolTaskExecutor`, the same outcome applies when the bean uses the same rejection policy and tasks genuinely reach the overload state. If the default `AbortPolicy` is selected, the third task will be rejected and **will not run on the caller**.

## 6. When Does `execute()` Return and Where Do Exceptions Go?

You cannot infer "finished" from the `;` at the end of `executor.execute(task);`.

| Mechanism | When does `execute` typically return? | Where does a `RuntimeException` thrown by the task appear? |
| --- | --- | --- |
| `SyncTaskExecutor` | After `Runnable.run()` finishes | Propagates immediately inside the caller's invocation |
| `SimpleAsyncTaskExecutor` | After handing off/starting the task; may be subject to concurrency limits | On the task's execution thread; the caller does not automatically receive the task exception |
| `ThreadPoolTaskExecutor` | After accepting the task, or throws if rejected | On the worker when the task runs; submission errors themselves may throw on the caller |
| Pool with `CallerRunsPolicy` when saturated | After the caller finishes running the task directly | May propagate on the caller, depending on the actual handler and wrappers |

The notes above describe **typical execution paths**; specific adapters, decorators, and policies can add behavior.

Error-prone example:

~~~java
try {
    taskExecutor.execute(() -> {
        throw new IllegalStateException("task failed");
    });
} catch (IllegalStateException e) {
    // Only guaranteed to catch the task exception if the task runs synchronously
    // and the exception propagates directly out of this call.
}
~~~

This is an **illustrative snippet** using an injected `taskExecutor` variable. With an asynchronous executor, the outer catch normally will not catch a failure occurring later on a worker. If you want the caller to have a point to wait and retrieve a result/failure, use a handle-returning API like `Future`, `CompletableFuture`, or design an appropriate result channel/queue.

You can use `CompletableFuture.runAsync(task, taskExecutor)` because `TaskExecutor` is also an `Executor`. However, returning a `CompletableFuture` **does not by itself guarantee** the task runs on another thread if the passed-in executor is direct/sync. `Future` is a mechanism for tracking completion and exceptions, not the thread-selection policy itself.

## 7. Implications in a Spring Application

### 7.1. A Controller Submitting Background Work May Not Have Handed It to a Background Thread

The following pattern receives a `TaskExecutor` via dependency injection:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    private final TaskExecutor executor;

    public ExportService(
            @Qualifier("applicationExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void exportLater(long reportId) {
        executor.execute(() -> generateReport(reportId));
    }

    private void generateReport(long reportId) {
        // Call business service or component to generate the report.
    }
}
~~~

**This is a Spring integration snippet, not a standalone Java SE program.** Behavior depends on the actual bean named `applicationExecutor`. If the bean is configured as a `SyncTaskExecutor`, calling `exportLater` **runs report generation on the current thread** before returning. If it is a normal thread pool, the task can run off the caller. If `CallerRunsPolicy` is configured, the task sometimes runs on the caller under saturation.

Therefore, design docs should state clearly **which executor bean**, **which implementation type**, **what pool/queue/rejection policy**, and **whether off-thread execution is mandatory**. Never claim something "runs in the background" solely because the code calls `execute`.

### 7.2. `@Async` Is a Different Mechanism, Yet You Still Must Know the Selected Executor

Spring provides `@Async` to execute methods via an interceptor and a configured executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    @Async("applicationExecutor")
    public void sendNotification(String recipient) {
        // Notification sending work.
    }
}
~~~

The application must enable `@EnableAsync` or an equivalent configuration. When invoked through the Spring proxy, the method is dispatched via the specified executor. **Self-invocation** (calling `this.sendNotification(...)` on the same instance in standard proxy mode) does not go through the proxy, so it does not trigger `@Async` interception. Do not confuse an active `@Async` call with calling `taskExecutor.execute(...)` directly; they have different integration mechanisms even when using the same executor.

The final semantics of task execution also depend on the executor bean and its policy. For business workflows that must run off the request-handling thread in every accepted case, you must verify both async interception and the executor strategy.

### 7.3. Transactions, Security Context, MDC, and `ThreadLocal`

A thread change is an **execution context** change, not merely a change in display name:

- With `SyncTaskExecutor`, the task runs on the caller and can see the `ThreadLocal` values and transaction associations attached to the caller at that moment.
- With a worker on another thread, transaction association, MDC tracing, request context, and security context are **not automatically copied over**. You must rely on framework-supported propagation mechanisms or pass data explicitly.
- Use `TaskDecorator` for appropriate metadata and ensure state is cleaned up after the task if you manage `ThreadLocal` yourself; avoid retaining request data across worker reuses.
- With `@Transactional`, the caller's transaction does not automatically "follow" a task running on another thread. If the task needs a transaction, design a transaction boundary for that execution unit.
- When a task occasionally runs on the caller due to `CallerRunsPolicy`, the issue is not just performance: assumptions about context, logging, transactions, and latency can differ from normal operation.

For that reason, do not use thread-locals as an undeclared channel to pass business data. Pass required values via arguments/messages and apply context propagation according to your needs.

### 7.4. TaskExecutor Does Not Automatically Make Shared State Thread-Safe

A task executor coordinates **execution**, not locking on a bean's mutable fields. If multiple workers increment `counter++` on a singleton `@Service`, lost updates can still occur. State must be protected with appropriate constructs (`AtomicInteger`, locks, immutable state, data-layer transactions, etc.), separating **thread-safety** requirements from **off-thread** requirements.

Even if `SyncTaskExecutor` only runs synchronously per call, two different requests can still call the same singleton from **two different caller threads**. Therefore, a "sync executor" also **does not guarantee** that the entire application is single-threaded.

## 8. Properly Testing Assumptions About Which Thread Runs a Task

When you need to verify an implementation/configuration, capture a reference to the caller thread, compare inside the task, and use a waiting mechanism so you do not read results prematurely.

**Illustrative** helper for an injected `TaskExecutor`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.core.task.TaskExecutor;

public class ExecutorThreadProbe {
    public static boolean runsOnCaller(TaskExecutor executor)
            throws InterruptedException {
        Thread caller = Thread.currentThread();
        AtomicReference<Thread> actual = new AtomicReference<>();
        CountDownLatch finished = new CountDownLatch(1);

        executor.execute(() -> {
            try {
                actual.set(Thread.currentThread());
            } finally {
                finished.countDown();
            }
        });

        if (!finished.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("task did not finish in time");
        }

        return actual.get() == caller;
    }
}
~~~

This snippet is a **test helper class**, without `main`. Once a real executor is supplied, the return value reports whether **that execution** used the caller. It does not prove every future run will behave identically, especially when policies change under load.

Do not use:

- `Thread.sleep(100)` and guessing the task has finished: the scheduler and machine load give no guaranteed deadline.
- Looking solely at thread names like `pool-1-thread-1`: names can be customized; compare the current `Thread` or check its id when needed.
- Looking solely at the timestamp order of two log lines: asynchronous logging, buffering, or timestamp resolution can lead to wrong conclusions.
- Writing tests that only verify `execute` throws no error: such tests do not measure whether the task finished or ran on another thread.
- Asserting "always off-thread" when the real configuration uses `CallerRunsPolicy` without generating load: the test can pass under light load and fail when the pool saturates.

**For testing strict invariants**, test normal paths, overload paths, shutdown, and rejection errors. For functional tests, use a latch/Future and assert business results rather than relying on a particular execution schedule.

## 9. Choosing an Execution Approach for Real Requirements

| Need | Suitable approach | Must verify further |
| --- | --- | --- |
| Want task to run immediately and sequentially on caller (e.g., unit tests) | `SyncTaskExecutor` | Runtime exceptions can propagate directly to the caller |
| Want each task to run on its own thread without a pool | `SimpleAsyncTaskExecutor` | Concurrency limits, resources, lifecycle |
| Want background processing with workers and a bounded queue | `ThreadPoolTaskExecutor` | Pool size, queue capacity, rejection policy, shutdown |
| Want to shed load by making the caller execute when saturated | `CallerRunsPolicy` | Caller latency can increase, task can run on caller |
| Need to stay off-thread even under overload | Configure executor to accept or **reject** transparently instead of caller-runs | Handle `TaskRejectedException`, retry/backpressure at the right layer |
| Need to know when a task finishes or receive failures | `Future` / `CompletableFuture` / completion signal | `Future` does not itself dictate the execution thread |
| Need durable processing surviving request and process termination | Queue/message broker or durable job mechanism | In-JVM `TaskExecutor` does not guarantee persistence, retry, or exactly-once |

You must distinguish **request latency**, **task acceptance conditions**, **behavior under saturation**, and **work reliability requirements**. A solution that is right for auxiliary work may be unsuitable for work that must process every order or never lose a notification.

## 10. Common Mistakes and How to Fix Them

**Mistake 1: "Calling `execute` definitely creates a new thread."**  
Fix: read the contract and check the implementation. `SyncTaskExecutor` runs immediately on the caller; `ThreadPoolTaskExecutor` usually reuses workers.

**Mistake 2: "It says `TaskExecutor`, so tasks are always async."**  
Fix: `TaskExecutor` is a general interface allowing both sync and async implementations; check `AsyncTaskExecutor` and the bean configuration if you need a specialized contract.

**Mistake 3: "A thread pool will absolutely never use the caller."**  
Fix: check `RejectedExecutionHandler`; `CallerRunsPolicy` makes the caller run the task when the pool is saturated.

**Mistake 4: "Once `execute` returns, the task is done."**  
Fix: only true with synchronous executors or additional synchronization. With async executors, use a latch, Future, or callback to observe completion.

**Mistake 5: "Returning fast proves the task ran on another thread."**  
Fix: a tiny sync task can also return fast; an async executor can block while waiting for a slot. Rely on thread identity and contract.

**Mistake 6: "If the task throws an exception, try/catch around `execute` always catches it."**  
Fix: distinguish submission errors from errors inside the worker. Use result handles, logging, or an exception handler accordingly.

**Mistake 7: "An injected Spring bean has a known fixed configuration."**  
Fix: use explicit qualifiers/bean names, check the implementation, queue, pool, and policy; test and production environments may configure different beans.

**Mistake 8: "`@Async` is enough, regardless of where it is called from."**  
Fix: ensure calls pass through the Spring proxy, enable async support, inspect the executor, and avoid self-invocation on the same instance in standard proxy mode.

**Mistake 9: "The task shares the caller's ThreadLocal/transaction."**  
Fix: tasks running on another thread need an explicit context propagation mechanism; caller-runs can cause behavior to differ between light and heavy load.

**Mistake 10: "A task running on the expected thread in one test proves the system always behaves that way."**  
Fix: test rejection/overload/shutdown paths as well and enforce design invariants rather than relying on logs from a single run.

## 11. Practice Scenarios

### Exercise 1: Read the Code and Predict Output

~~~java
TaskExecutor executor = new SyncTaskExecutor();
System.out.println("A");
executor.execute(() -> System.out.println("B"));
System.out.println("C");
~~~

**Answer:** `A`, `B`, `C` in order because `SyncTaskExecutor` calls `run()` directly. The illustrative snippet needs Spring on the classpath, imports, and an enclosing method to run.

### Exercise 2: Can a Thread Pool Slow Down HTTP Requests?

A controller calls `execute(...)` on a pool with 2 workers, queue 10, and `CallerRunsPolicy`. Under high load, why does request latency spike suddenly?

**Answer:** when both workers are busy and the queue is full, the handler runs the task on the request thread itself. The controller only continues after the task completes; this acts as backpressure, but can break the assumption that the task always runs in the background.

### Exercise 3: Which Statements Are True?

1. If `execute` returns `void`, the task runs synchronously.
2. `TaskExecutor` does not preclude synchronous implementations.
3. Both `SimpleAsyncTaskExecutor` and `ThreadPoolTaskExecutor` must create a new thread for each task.
4. `CallerRunsPolicy` can cause a task to run on the caller when the pool is overloaded.

**Answer:** (2) and (4). A `void` return type does not dictate when or where execution occurs; thread pools normally reuse workers.

### Exercise 4: How to Prove Reliably That a Job Finished?

A test calls `executor.execute(job)` and then immediately runs `assertEquals(1, result.get())`. The test is flaky with an async executor.

**Answer:** if you need to wait for the job to complete, pass a `CountDownLatch`/`Future` and wait with a timeout before asserting. Do not insert `sleep`. If there is also a requirement that "the task must not run on the request thread," verify/constrain the executor and policy separately.

## 12. Code Review Checklist for `execute(Runnable)`

1. **Which executor?** Are the bean name, concrete class, and runtime configuration clear?
2. **Which thread?** Is off-thread execution mandatory? Does the contract guarantee it, or is it merely inferred from the method name?
3. **What happens under overload?** Are queue, max threads, `CallerRunsPolicy`, `AbortPolicy`, and shutdown designed?
4. **Can the caller block?** Impact on latency and execution within request transactions must be identified.
5. **How do we know the task finished?** Latch, Future, callback, job status, or result message?
6. **Where are errors handled?** Task acceptance errors differ from exceptions inside the task.
7. **Which context is propagated?** Transactions, security, MDC, request data, and ThreadLocal.
8. **Is shared state safe?** An executor does not protect a singleton's mutable fields for you.
9. **Do tests control interleaving and overload scenarios?** Avoid relying on `sleep` or log ordering.

## 13. Key Takeaways

- `execute(Runnable)` describes **submitting a task to an executor**; it **does not implicitly require running on another thread**.
- `SyncTaskExecutor` executes **synchronously on the caller**, whereas `SimpleAsyncTaskExecutor` and `ThreadPoolTaskExecutor` are designed for asynchronous work with different thread-management characteristics.
- Even with a thread pool, `CallerRunsPolicy` can shift tasks onto the caller under overload; the rejection policy also determines whether a task is accepted at all.
- Do not use return speed, method names, timestamps, or `Thread.sleep` to prove thread identity or completion. Inspect the contract/config and use proper synchronization primitives.
- In Spring, real-world impact also involves request latency, `@Async` proxies, transactions, security/MDC context, exception handling, and executor lifecycle.

## References

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — `TaskExecutor` (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework Javadoc — `SyncTaskExecutor` (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/SyncTaskExecutor.html
- Spring Framework Javadoc — `AsyncTaskExecutor` (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html
- Java SE 17 — `Executor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 17 — `ThreadPoolExecutor` and rejection handlers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
