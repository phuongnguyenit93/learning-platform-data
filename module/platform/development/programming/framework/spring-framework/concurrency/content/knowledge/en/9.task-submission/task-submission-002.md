# Submitting Runnable or Callable via submit() in Spring Framework

## 1. Why Use submit() Instead of Calling execute() Alone?

An application often has tasks such as generating reports, calculating scores, processing input data, or sending notifications. A business component wants to **submit a task for an executor to run**, while potentially needing to know when the task completes, receive the computed value, or know whether the task failed.

When you only want to request execution, the `execute(Runnable)` contract suffices. However, when you need **a handle to track the outcome**, the `submit(...)` methods are more convenient because they return a `Future`.

In Java and Spring, the two fundamental task forms are:

- **`Runnable`**: an action with a `run()` method that returns no value. Suitable for tasks producing side effects such as writing audits, updating metrics, or dispatching events.
- **`Callable<T>`**: a task with a `call()` method that returns a `T` and may declare checked exceptions. Suitable when the caller needs a processing result.

Example:

```java
Runnable audit = () -> System.out.println("Audit stored");

Callable<Integer> score = () -> 10 * 2 + 1;
```

These two lines only **create the tasks**, without submitting them to an executor yet. This is a fragment; it requires importing `java.util.concurrent.Callable` and can be placed inside a normal Java method.

Task submission typically follows this lifecycle:

```text
caller
  | submit(Runnable / Callable)
  v
executor -- accept / queue / schedule --> worker thread --> task.run()/call()
  |
  +-- return Future immediately (for an async executor)
          |
          +-- get() / get(timeout) -> value or exception
          +-- isDone(), isCancelled(), cancel(...)
```

The model above applies to an executor that truly runs asynchronously. An implementation of `AsyncTaskExecutor` may use a different specific execution policy, so check the bean in use; **submit does not automatically guarantee the task runs on a new thread**.

## 2. Use the Right Interface: TaskExecutor, AsyncTaskExecutor, and ExecutorService

In Spring Framework 6.x, common types have different capability levels:

| Type | Primary API | Has submit(Runnable/Callable)? | Role |
| --- | --- | --- | --- |
| `java.util.concurrent.Executor` | `execute(Runnable)` | No | Minimal JDK contract |
| `org.springframework.core.task.TaskExecutor` | `execute(Runnable)` | No | Basic executor interface in Spring, extending `Executor` |
| `org.springframework.core.task.AsyncTaskExecutor` | `execute(...)` and `submit(...)` | Yes | Spring interface when the caller wants a `Future` |
| `java.util.concurrent.ExecutorService` | `execute`, `submit`, `shutdown`... | Yes | JDK executor with result and lifecycle management APIs |
| `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` | Supports `AsyncTaskExecutor`, runs on a pool | Yes | Spring executor bean with configuration and lifecycle management |

**A very common compile error:**

```java
TaskExecutor executor = /* Spring-managed executor */;
// executor.submit(() -> 42); // DOES NOT compile: TaskExecutor does not declare submit().
executor.execute(() -> System.out.println("Run without Future"));
```

If a service genuinely needs a `Future`, inject the `AsyncTaskExecutor` interface (or `ExecutorService` if the design depends on the JDK service interface). Do not cast an arbitrary `TaskExecutor` to `ThreadPoolTaskExecutor` just to call `submit`; doing so couples business logic to an implementation and can cause a `ClassCastException`.

When using a Spring-managed `ThreadPoolTaskExecutor`, you can inject it by the **`AsyncTaskExecutor` interface type**. This allows swapping compatible executors in configuration without modifying business services.

## 3. Distinguishing submit(Runnable) and submit(Callable<T>)

### 3.1. submit(Runnable): Tracking Completion

Signature:

```java
Future<?> submit(Runnable task);
```

Use when the task **does not produce a direct return value**:

```java
Runnable task = () -> counter.incrementAndGet();
Future<?> future = asyncExecutor.submit(task);
Object result = future.get(); // null if the task finishes normally.
```

This is a fragment, requiring `counter` and `asyncExecutor` variables to be declared and checked exceptions from `get()` to be handled.

Key points to grasp:

- `Future.get()` waits until the `Runnable` finishes; **the return value is `null`** if the task succeeds.
- `null` does not prove the task "did nothing": side effects may have occurred.
- If `Runnable.run()` throws an exception and the implementation stores the error via the `Future`, `get()` will throw `ExecutionException` with the root cause in `getCause()`.
- `submit` may reject the task right at submission time, for example `TaskRejectedException` from `ThreadPoolTaskExecutor` when the pool and queue are overloaded.

### 3.2. submit(Callable<T>): Receiving a Value or an Error

Signature:

```java
<T> Future<T> submit(Callable<T> task);
```

Use when the task **produces a result**:

```java
Callable<Integer> task = () -> 10 * 2 + 1;
Future<Integer> future = asyncExecutor.submit(task);
Integer value = future.get(); // 21 when the task succeeds.
```

`Callable.call()` can throw checked exceptions, whereas `Runnable.run()` does not declare `throws Exception`. Even so, runtime exceptions from both task types must be observed through the `Future` and the executor's handling behavior.

### 3.3. Outcome Table to Remember

| Invocation | Return type of submit | Value from Future.get() on success | Task failure |
| --- | --- | --- | --- |
| `submit(Runnable)` | `Future<?>` | `null` | Typically `ExecutionException` wrapping cause |
| `submit(Callable<String>)` | `Future<String>` | String returned by `call()` | `ExecutionException` |
| `submit(Callable<Integer>)` | `Future<Integer>` | Integer returned by `call()` | `ExecutionException` |

In Spring Framework 6.1+, `AsyncTaskExecutor` has default implementations for both `submit` overloads that create a `FutureTask` and delegate to `execute`. Implementations like `ThreadPoolTaskExecutor` may override the methods to use the internal executor service directly. **The outcome contract** is the same, while execution details depend on the implementation.

### 3.4. Overloads and Lambdas: Do Not Leave Intent Ambiguous

An expression lambda that invokes a method can fit both value-producing and statement forms. When reading code, explicit type declarations can help avoid overload confusion:

```java
Runnable update = () -> counter.incrementAndGet();
Callable<Integer> calculate = () -> 10 * 2 + 1;

Future<?> updated = asyncExecutor.submit(update);
Future<Integer> calculated = asyncExecutor.submit(calculate);
```

The variables `counter` and `asyncExecutor` are dependencies in this fragment. Typing as `Runnable` or `Callable<T>` makes clear to readers whether the author expects a return value.

## 4. What Does a Future Represent?

`Future<V>` is a **handle** to an asynchronous computation. It does not store a full copy of business state on its own, does not guarantee durability across restarts, and is not a tool for observing every task in the system.

Core operations:

- `get()`: waits indefinitely until the task completes, is cancelled, or fails. If the caller is interrupted while waiting, it may throw `InterruptedException`.
- `get(timeout, unit)`: waits up to a specified duration; if not yet complete, throws `TimeoutException`. It **does not automatically cancel** the running task.
- `isDone()`: true if completed normally, via error, or via cancellation; **does not mean success**.
- `isCancelled()`: indicates whether the `Future` was cancelled through the cancellation mechanism.
- `cancel(true)`: attempts to cancel and allows interrupting the worker if the task is running. Returning true does not guarantee the task code stops immediately.
- `cancel(false)`: attempts to cancel without requesting an interrupt on an already-running task. For a task waiting in the queue, it may prevent execution, depending on the implementation.

Timeout handling skeleton example:

```java
try {
    String value = future.get(2, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException ex) {
    // Task may still be running.
    future.cancel(true); // Only if business logic permits stopping.
}
```

This is a **fragment**; `future` is `Future<String>`, `use` is a business method, requiring imports for `TimeUnit` and `TimeoutException`, as well as handling or declaring `InterruptedException`/`ExecutionException`. Do not blindly call `cancel(true)` if the submitted work has side effects that must not be abandoned midway.

**Memory relationship:** in the JDK, actions performed inside the task *happen-before* actions in another thread after that thread successfully returns from the corresponding `Future.get()`. Therefore, tests can check side effects after `get()` without sleeping for a guessed duration.

## 5. Runnable Spring Framework 6.2.1 Example with Java 21

The complete program demonstrates:

1. Injecting `AsyncTaskExecutor` into a service via constructor.
2. Submitting a `Runnable` with side effects and observing the `null` result.
3. Submitting a `Callable<Integer>` and receiving the value.
4. Submitting a failing `Callable` and reading the cause via `ExecutionException`.
5. Using `CountDownLatch` to simulate a waiting task; `get(timeout)` throws a timeout, yet the task still proceeds after being released.

### 5.1. Project Structure

```text
spring-submit-demo/
├── pom.xml
└── src/main/java/demo/SubmitTaskDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-submit-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <configuration>
          <mainClass>demo.SubmitTaskDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**File `src/main/java/demo/SubmitTaskDemo.java`:**

```java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SubmitTaskDemo {
    public static final class JobService {
        private final AsyncTaskExecutor executor;
        private final AtomicInteger auditCount = new AtomicInteger();

        public JobService(AsyncTaskExecutor executor) {
            this.executor = executor;
        }

        public Future<?> recordAudit() {
            Runnable task = () -> auditCount.incrementAndGet();
            return executor.submit(task);
        }

        public int auditCount() {
            return auditCount.get();
        }

        public Future<Integer> calculate(int input) {
            Callable<Integer> task = () -> input * 2 + 1;
            return executor.submit(task);
        }

        public Future<Integer> fail() {
            Callable<Integer> task = () -> {
                throw new IllegalStateException("example error");
            };
            return executor.submit(task);
        }

        public Future<String> waitForRelease(
                CountDownLatch started, CountDownLatch release) {
            Callable<String> task = () -> {
                started.countDown();
                release.await();
                return "released";
            };
            return executor.submit(task);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("jobExecutor")
        public ThreadPoolTaskExecutor jobExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("job-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        public JobService jobService(
                @Qualifier("jobExecutor") AsyncTaskExecutor executor) {
            return new JobService(executor);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            JobService jobs = context.getBean(JobService.class);

            Future<?> audit = jobs.recordAudit();
            System.out.println("Runnable result=" +
                    audit.get(5, TimeUnit.SECONDS));
            System.out.println("Audit count=" + jobs.auditCount());

            Future<Integer> value = jobs.calculate(10);
            System.out.println("Callable result=" +
                    value.get(5, TimeUnit.SECONDS));

            Future<Integer> failure = jobs.fail();
            try {
                failure.get(5, TimeUnit.SECONDS);
                throw new AssertionError("Expected task failure");
            } catch (ExecutionException ex) {
                System.out.println("Failure cause=" +
                        ex.getCause().getClass().getSimpleName());
            }

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            Future<String> slow = jobs.waitForRelease(started, release);
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            try {
                slow.get(20, TimeUnit.MILLISECONDS);
                throw new AssertionError("Expected timeout");
            } catch (TimeoutException expected) {
                System.out.println("Timeout observed=true");
            } finally {
                release.countDown();
            }
            System.out.println("After release=" +
                    slow.get(5, TimeUnit.SECONDS));
        }
    }
}
```

### 5.2. Running the Program

Requires JDK 21 or later and Maven installed. Inside the `spring-submit-demo` directory, run:

```bash
mvn -q -DskipTests compile exec:java
```

Verified output of the compiled and executed program:

```text
Runnable result=null
Audit count=1
Callable result=21
Failure cause=IllegalStateException
Timeout observed=true
After release=released
```

The configuration uses `maven.compiler.release=21` to ensure the source compiles for Java 21; the output above is the program's output, excluding auxiliary logs that may appear depending on the Maven/JVM version.

### 5.3. Why Is the Output Deterministic?

- `audit.get(...)` only returns after the `Runnable` task finishes; therefore `auditCount` has already incremented before printing.
- `calculate(10)` returns `21` via `Future<Integer>`.
- `fail()` throws `IllegalStateException` inside the worker; `Future.get(...)` on the caller throws `ExecutionException`, whose `getCause()` is the original exception.
- The `waitForRelease(...)` task signals it has started via `started.countDown()`, then waits on `release.await()`; the caller is guaranteed not to have a result before opening the latch, so `get(20, MILLISECONDS)` takes the timeout branch.
- After `release.countDown()`, the task can continue and `get(...)` returns `"released"`; timing out on the caller **does not automatically cancel** the work.
- The program closes the Spring context with `try-with-resources`. Because the executor is a Spring-managed bean, its lifecycle is managed. All tasks have completed before the context closes.

All output is printed from the main thread after observing the `Future`; no natural execution order among workers is assumed when multiple tasks are submitted concurrently.

## 6. Sequence for Handling Results and Errors

A `Future<T>` can end in different terminal states.

### 6.1. Success

With `Callable<T>`, `get()` returns the value from `call()`. With `Runnable`, `get()` returns `null` if no error occurs.

### 6.2. Failure Inside the Task

If the task throws an exception, `Future.get()` throws `ExecutionException`; `ExecutionException.getCause()` is the error from the task. With `ThreadPoolTaskExecutor.submit(...)`, an error inside the task is typically held inside the `FutureTask`, so **you should not rely solely on worker logs being sufficient**.

A handling pattern when waiting with a bound:

```java
try {
    Integer result = future.get(3, TimeUnit.SECONDS);
    save(result);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log/categorize the business error from the worker.
} catch (TimeoutException ex) {
    // Add appropriate timeout/cancel/retry policy.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Let the caller decide how to terminate/back out of the task.
}
```

This is a **fragment**: `future` is of type `Future<Integer>`, `save` is a business method, requiring imports `TimeUnit`, `ExecutionException`, and `TimeoutException`. The pattern uses `Thread.currentThread().interrupt()` when the caller decides not to propagate `InterruptedException`, preserving the interruption signal. If the method contract permits, `InterruptedException` can be propagated upward.

### 6.3. Timeout While Waiting

`TimeoutException` only states that the result was not ready *within the caller's wait budget*. The task may continue and succeed afterward. When a timeout occurs, decide whether the caller should discard the result, retry, cancel, or store status for later querying.

Do not immediately retry a task that produces side effects upon timeout without an idempotency key: the previous attempt may complete later, causing duplicate execution.

### 6.4. Cancelled Task

When `Future.cancel(true)` succeeds, `Future.get()` will throw `CancellationException`. If the task is already running, interruption is only a cooperative request; the task might not stop immediately. Certain I/O calls, native APIs, or code that ignores interrupts may continue working.

If work cancellation is needed, design tasks with interruption checkpoints, close resources properly, and record appropriate status. Do not treat `cancel(true)` as a transaction rollback or an undo of already-written side effects.

### 6.5. Error Immediately at Submission Time

`ThreadPoolTaskExecutor.submit(...)` can throw `TaskRejectedException` if the executor does not accept the task due to saturation or shutdown. This happens **right at submit**, before there is a valid `Future` for the caller to wait on.

Separation pattern:

```java
try {
    Future<Integer> submitted = asyncExecutor.submit(
            (Callable<Integer>) () -> 21);
    // At this point we have a handle to process the value/error after execution.
} catch (TaskRejectedException ex) {
    // No new task was accepted; handle overload on the caller.
}
```

This is a fragment requiring imports for `Callable`, `Future`, and `TaskRejectedException`; `asyncExecutor` is a declared dependency. Succeeding at `submit` means the task was accepted according to the executor's policy, **not** a guarantee that the task has run successfully.

## 7. Distinguishing execute(), submit(), and submitCompletable()

In Spring Framework 6.x:

| API | Parameter | Return value | When appropriate |
| --- | --- | --- | --- |
| `TaskExecutor.execute(Runnable)` | `Runnable` | `void` | No result handle needed |
| `AsyncTaskExecutor.submit(Runnable)` | `Runnable` | `Future<?>` | Need to know if the task completed, failed, or was cancelled |
| `AsyncTaskExecutor.submit(Callable<T>)` | `Callable<T>` | `Future<T>` | Need a result of type `T` |
| `AsyncTaskExecutor.submitCompletable(Runnable)` | `Runnable` | `CompletableFuture<Void>` | Want to chain callbacks when a void task completes |
| `AsyncTaskExecutor.submitCompletable(Callable<T>)` | `Callable<T>` | `CompletableFuture<T>` | Want to compose results via CompletionStage |

`CompletableFuture` provides APIs such as `thenApply`, `thenCompose`, `allOf`, and `exceptionally`, suitable when composing async steps without actively calling `get()` at each step. However, callbacks may run on the thread completing the stage or another executor depending on the method; you must understand the execution context.

Use `submitCompletable(...)` when you genuinely need chaining. For the problem of "submitting a `Runnable` or `Callable` and obtaining a `Future`", the two `submit(...)` overloads are sufficient.

**`@Async` is not synonymous with `submit(...)`.** `@Async` is a Spring proxy-based interceptor for eligible methods, enabled via `@EnableAsync` or XML annotation-driven configuration. Calling `asyncExecutor.submit(...)` directly does not require `@EnableAsync` and does not depend on `@Async`'s proxy/self-invocation rules.

## 8. Do Not Call get() in the Wrong Place

`submit()` normally returns quickly once the executor accepts the task, allowing the caller to do other work. However:

```java
Integer value = asyncExecutor.submit(
        (Callable<Integer>) () -> expensiveCalculation()).get();
```

If `expensiveCalculation()` takes a long time, writing it this way makes the caller **block immediately after submit**. This may make sense when the result is needed right away, but yields no asynchronous benefit for the caller. The snippet is a fragment requiring `expensiveCalculation` to exist and checked exceptions to be handled.

Common issues:

- **In Spring MVC:** keeping a servlet request thread waiting on `Future.get()` can exhaust request workers under load. Consider a task-status API design or async request handling if appropriate for the business case.
- **In a Reactor event loop:** calling blocking `get()`/`join()` can stall the event-loop thread and increase latency across many requests; never perform blocking calls on an event loop.
- **Inside the same small thread pool:** Task A holds a worker and calls `submit(B).get()` on *that same pool*, while all workers are waiting on other subtasks. Those subtasks sit in the queue and can never run — **thread starvation deadlock**. Eliminate nested waiting or separate orchestration from the worker pool, changing the dependency structure rather than arbitrarily enlarging the pool.
- **In HTTP/APIs with short timeouts:** using `get(timeout)` while forgetting timeouts on the DB/HTTP client inside the task can leave the worker running long after the caller has given up.

### Typical Deadlock Scenario

Suppose a pool has `corePoolSize=maxPoolSize=1` and the queue still has capacity:

```text
Worker-1 executes task A
    -> A submits(task B) to the same pool
    -> B sits in the queue
    -> A calls B.get() and waits
    -> Worker-1 cannot pick up B because it is still running A
    -> No other workers -> no progress possible
```

This is a deadlock caused by workflow design, **not a bug in Future**. Merely increasing `queueCapacity` keeps B waiting without resolving the circular dependency.

## 9. Sizing the Executor and Controlling Overload

`ThreadPoolTaskExecutor` uses `ThreadPoolExecutor` under the hood, so `submit` is subject to the same execution bounds as `execute`.

- **`corePoolSize`:** core worker count; the pool typically spawns workers up to this threshold before queuing.
- **`queueCapacity`:** number of tasks that can wait in the queue, excluding currently running tasks. With a positive value, Spring typically uses `LinkedBlockingQueue`; with 0, it uses `SynchronousQueue`, holding no backlog.
- **`maxPoolSize`:** upper limit on total workers; once the queue accepts tasks, the pool typically does not scale beyond core until the queue is full.
- **Rejection policy:** when unable to accept a task, the default typically throws a rejection error. Other policies can be configured, but their consequences must be understood.
- **Shutdown:** a shutting-down executor may stop accepting new tasks; having been submitted does not imply any mechanism guarantees the task survives a restart.

In the complete program example: `core=2`, `max=2`, `queue=8` is merely a bounded learning configuration. Do not reuse these exact numbers for every application; measure throughput, queue wait, active tasks, CPU, I/O wait time, connection pool limits, and rejections.

Distinguish two kinds of time:

1. **Queue wait:** from submission until a worker starts executing.
2. **Execution time:** from when the worker starts until the task finishes.

The time from `submit` until `Future.get()` returns a result can include both, plus scheduler/caller overhead. Looking solely at `Future.isDone()`, you cannot tell whether the bottleneck is in the queue or inside the task.

### When Is Backpressure Needed?

If task arrival rate exceeds processing rate for a sustained period, a bounded queue will fill up. Configuring an unbounded queue can turn rejections into severe latency and memory retention. Apply input limits, retries with backoff, timeouts, and explicit load-shedding policies. For business workflows requiring guaranteed delivery, consider durable messaging/outbox; an in-memory executor only operates within the current process.

## 10. Exception Visibility and Monitoring

An important operational difference between `execute` and `submit` is **the path an exception takes**.

With `submit`, the task is usually wrapped in a `FutureTask`; exceptions inside are captured so `Future.get()` can report them to the caller. They may **not** be seen by a worker's `UncaughtExceptionHandler` as an exception escaping directly from `run()`.

Consequences:

- If you call `submit` and completely discard the `Future`, errors may go unrecorded where you expect them.
- A Spring `TaskDecorator` typically sees the execution wrapper; with `submit`, it may see a `FutureTask` instead of the original `Runnable/Callable`. To observe errors, you must design hooks/metrics or read outcomes according to contract.
- `ThreadPoolExecutor.afterExecute(...)` may need to inspect the `Future` to extract errors from submitted tasks; do not assume the `Throwable` parameter always holds the task error.
- For critical tasks, a clear owner must be responsible for checking the `Future`, logging errors, updating status, or emitting failure events.

Do not call an unbounded `Future.get()` inside an instrumentation callback on a worker thread where it could deadlock; only read the result when the Future is guaranteed to be done and handle cancellation/exceptions properly.

## 11. Thread Safety, Transactions, and Caller Context

Submitting a task to a pool means task code can run on a **different thread** and at a **different time**.

### 11.1. Thread Safety

Multiple tasks can run concurrently, accessing a singleton service or shared data. Use immutable inputs, `AtomicInteger`, intentional synchronization, or thread-safe data structures when needed. The example uses `AtomicInteger` so side effects from `Runnable` remain safe across concurrent worker updates.

### 11.2. Transactions

Submitting a `Callable` inside a `@Transactional` method does not automatically propagate the current transaction to the worker thread. Transaction context is normally thread-bound; the task needs its own transaction if it performs DB work. Furthermore, if submitted before the caller's transaction commits, the task may read uncommitted/unready data or have mismatched side effects if the caller rolls back.

For work that must occur **after commit**, consider `@TransactionalEventListener(phase = AFTER_COMMIT)` or the outbox pattern depending on durability needs. Do not rely on the executor to maintain transactional ordering or consistency.

### 11.3. Security and Log Context

The calling thread's MDC, `SecurityContext`, and `ThreadLocal` values do not automatically appear on the worker. If you need a correlation ID or principal, pass the needed fields explicitly and safely or use a properly configured context propagation mechanism / task decorator. Avoid passing mutable request objects or retaining security credentials in queues longer than necessary.

### 11.4. Cancellation and Resource Cleanup

Tasks should respect interruption when appropriate; close socket/file/DB resources in `try-finally` or `try-with-resources`. For tasks that have already written partial side effects, cancellation does not restore data; idempotency, transactions, or compensating actions are needed depending on business logic.

## 12. Testing submit Without Relying on Sleep

A unit test does not necessarily require a real thread pool. If a service only requires `AsyncTaskExecutor`, you can use a fake executor or an appropriate synchronous implementation to test task submission. When real concurrency must be tested, use `CountDownLatch` or `Phaser` to control milestones rather than `Thread.sleep(100)` hoping the worker has run.

In the sample program, the two latches have specific roles:

- `started` ensures the worker has reached the wait point.
- `release` ensures the caller tests the timeout branch before the task is released.

Short test pattern requiring an existing `AsyncTaskExecutor executor`:

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

Future<String> task = executor.submit(() -> {
    started.countDown();
    release.await();
    return "done";
});

try {
    if (!started.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Worker did not start");
    }

    try {
        task.get(20, TimeUnit.MILLISECONDS);
        throw new AssertionError("Expected timeout");
    } catch (TimeoutException expected) {
        // Expected: task is still waiting on release.
    }
} finally {
    release.countDown();
}

if (!"done".equals(task.get(5, TimeUnit.SECONDS))) {
    throw new AssertionError("Unexpected result");
}
```

This is a **fragment** requiring imports for `CountDownLatch`, `Future`, `TimeUnit`, `TimeoutException` and handling of checked exceptions. The task is released in `finally` to avoid leaving a worker stuck if an assertion fails.

Unit tests for a pure `Callable<Integer>` do not need a Spring context; integration tests are where you verify bean wiring, pool sizing, rejection, lifecycle, and actual threading.

## 13. Common Mistakes When Using submit()

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Calling `submit` on a `TaskExecutor` variable | The interface does not declare `submit` | Inject `AsyncTaskExecutor` when a `Future` is needed |
| Assuming `submit(Runnable).get()` returns a lambda's value | `Runnable.run()` is `void` | Use `Callable<T>` to produce `T` |
| Calling `submit` and discarding `Future` while expecting error visibility | Errors may sit in the Future with no consumer | Observe via `get` or proper error reporting |
| Calling `get()` directly on a servlet/event loop | Blocks the caller, hurting throughput | Avoid blocking on latency-sensitive paths |
| Using `get(timeout)` and assuming the task was cancelled | Timeout only applies to the caller | Handle cancellation/cleanup explicitly |
| Calling `cancel(true)` and assuming rollback happened | Interrupt is a signal; side effects may already be written | Design idempotency, transactions, cleanup |
| Ignoring `ExecutionException.getCause()` | Loses the real root cause of failure | Categorize/log the cause in the right place |
| Treating `isDone()==true` as success | Done state includes failure and cancellation | Use `get`/`isCancelled` to inspect the outcome |
| Submitting a child task and calling `get()` inside the same small pool | Can cause starvation deadlock | Avoid nested blocking, adjust orchestration |
| Raising `maxPoolSize` while keeping a huge queue | The queue fills before extra threads beyond core are spawned | Measure queue wait and tune core/queue/max together |
| Using `submit` instead of durable messaging | Futures and in-memory queues are lost on process crash | Use a broker/outbox if durability is required |
| Assuming ThreadLocal/transactions automatically propagate to workers | Thread context is normally not shared | Pass data explicitly, configure propagation when needed |

## 14. Reasoning Exercises

**Exercise 1.** What type is the following task, and what does `Future.get()` return?

```java
Runnable r = () -> System.out.println("saved");
Future<?> f = executor.submit(r);
```

Answer: it is a `Runnable`. If the task completes normally, `f.get()` returns `null`; the text `saved` is a printed side effect. The fragment requires `AsyncTaskExecutor executor` to be declared.

**Exercise 2.** Given a `Callable<String>` returning `"ok"`, what does `Future<String>.get()` produce?

Answer: it returns `"ok"` on normal completion; if the task throws an exception, the caller receives `ExecutionException`; if interrupted while waiting, the caller receives `InterruptedException`.

**Exercise 3.** A caller receives `TimeoutException` from `future.get(1, SECONDS)` and then retries the same email-sending task. Is the email guaranteed to be sent only once?

No. The earlier Future may still be running and finish after the timeout. For safe retries, use an idempotency key, job state, or a durable delivery solution suited to business needs.

**Exercise 4.** Why does `Future.isDone()==true` not prove the task succeeded?

Because the done state also includes failed or cancelled tasks. You must inspect the result or exception with `get()` and check for cancellation.

**Exercise 5.** A Spring service currently only receives `TaskExecutor` but needs to return `Future<Integer>`. Should it cast to `ThreadPoolTaskExecutor`?

No. Express the required dependency as `AsyncTaskExecutor` and configure an appropriate bean. That keeps business logic decoupled from the implementation.

## 15. Checklist for Applying in a Spring Application

Before using `submit` in production, verify:

1. **API:** Does the client need a result or only side effects? Pick `Runnable` or `Callable<T>` and the `AsyncTaskExecutor` interface matching the capability.
2. **Bean:** Does the injected executor bean have the right name, core/max/queue/rejection settings, and lifecycle? Could pools be mixed up?
3. **Outcome:** Who reads the `Future`, handles `ExecutionException`, `CancellationException`, and `TaskRejectedException`, and records the final status?
4. **Timeout:** Are sensible limits set on the Future and on DB/HTTP calls inside the task? When the caller times out, does the task keep running or get cancelled under a defined policy?
5. **Context:** Will transactions, security, MDC, and input data still be valid when the worker runs later?
6. **Concurrency:** Is there nested blocking or interdependent tasks inside the same small pool? Are downstream quotas sufficient?
7. **Operations:** Are active threads, queue size, queue wait, execution time, rejections, errors, and memory observed under real load?
8. **Durability:** Must the task survive restarts? If yes, an in-memory executor with Future is not enough.

**Remember:** `submit(Runnable)` lets you track **the completion** of an action with no return value, while `submit(Callable<T>)` lets you track **a result of type T**. Both return a `Future` so the caller can learn of success, failure, timeout, or cancellation; execution decisions, resource bounds, and lifecycle still belong to the configured executor.

### References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java 21 — Future Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 21 — ExecutorService Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)