# Timed `get()`: Retrieving Task Results in Spring Framework

## Objectives

When submitting a task to an executor, the calling thread typically receives a `Future<T>` or `CompletableFuture<T>` before the result is actually ready. Calling an unbounded `get()` can block the waiting thread for a very long time if the task stalls on I/O, blocks on a lock, waits in a queue, or never completes. Java provides the **`get(long timeout, TimeUnit unit)`** variant so callers can enforce a **maximum wait time for a single result retrieval**.

This lesson focuses on using bounded wait times in the context of Spring Framework concurrency, where tasks may be submitted via `AsyncTaskExecutor`, `ThreadPoolTaskExecutor`, or an `@Async` method returning `Future`/`CompletableFuture`.

After this lesson, you will:

1. Correctly read the contract of `Future.get(timeout, unit)` and distinguish it from unbounded `get()`.
2. Handle success, `TimeoutException`, `ExecutionException`, `InterruptedException`, and `CancellationException` separately.
3. Understand that **caller wait timeout does not automatically cancel the task on the worker**.
4. Use timed `get` with Spring `@Async`, knowing which thread is waiting and which thread is executing.
5. Distinguish a result wait timeout from HTTP client/database timeouts, overall request timeouts, multi-task workflow deadlines, and `CompletableFuture.orTimeout`.
6. Choose post-timeout behavior (return error, fallback, continue background processing, controlled cancellation) without losing results or holding resources indefinitely.

## 1. What Is `Future` and Where Does `get()` Wait?

`Future<T>` is **an object representing the result of a computation that may not yet have completed**. It is typically returned by `ExecutorService.submit(...)`, `AsyncTaskExecutor.submit(...)`, or a Spring `@Async` call with an eligible return type.

```text
Caller thread                   Executor / worker thread
    |                                      |
    | submit task ----------------------->|  task executes
    |<------------ Future<T> -------------|
    |                                      |  (may still be processing)
    | future.get(timeout, unit)            |
    |     [caller waits for result]        |
    |                                      |
    |<------------- value / error --------|
    | caller continues                     |
```

**Key point:** whichever thread calls `get()`, **that thread waits**. `get(timeout, unit)` does not offload waiting to a new worker, does not auto-grow the pool, and does not turn blocking I/O into non-blocking I/O. In Spring MVC, if a request thread calls `get(...)`, that request thread itself can block for the wait duration.

A future may already be complete before the caller invokes `get`; in that case the method returns immediately (or throws the recorded error/cancellation). A wait timeout **does not force waiting for the full timeout duration**.

## 2. Signature and Meaning of the Timeout

Java 17 defines on `java.util.concurrent.Future<V>`:

```java
V get(long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;
```

Example:

```java
String result = future.get(500, TimeUnit.MILLISECONDS);
```

Interpretation:

- `500` is the length of the **wait time for this `get` call**, not the maximum task duration measured from submission.
- `TimeUnit.MILLISECONDS` specifies the unit. `SECONDS`, `MICROSECONDS`, `NANOSECONDS`, and other units may be used.
- If the result has already completed successfully, returns value `V`.
- If no result is available after the allowed wait time, throws `TimeoutException`.
- If the task failed, throws `ExecutionException` with the real cause in `getCause()`.
- If the **waiting** thread is interrupted, throws `InterruptedException`.
- If the future was cancelled, may throw `CancellationException` (unchecked).

The no-arg `get()` differs in that it can wait until the future finishes (or is interrupted/cancelled), with **no caller-imposed deadline**. It is therefore unsuitable when a request has a strict deadline and a task might hang.

### Result Table

| Condition at or during the wait | `future.get(500, MILLISECONDS)` | What should the caller do? |
| --- | --- | --- |
| Succeeds within the limit | Returns `T` | Process the result normally. |
| Task still incomplete when limit expires | Throws `TimeoutException` | Choose error response/fallback/cancel; do not implicitly assume the task stopped. |
| Task completes with an exception | Throws `ExecutionException` | Inspect `getCause()`, record and classify the business error. |
| Waiting thread is interrupted | Throws `InterruptedException` | Restore interrupt flag if not handled higher up; exit waiting cleanly. |
| Future is cancelled | Throws `CancellationException` | Handle cancelled status; do not try to treat as success. |

A future with `isDone() == true` can be **succeeded, failed, or cancelled**. `isDone()` does not mean "has a successful value"; `isCancelled()` only tells you it was cancelled. Between checking `isDone()` and handling the outcome, state can still change (unless already completed); usually you should call `get(...)` directly and handle exceptions.

### Why Does Timing Out Not Mean the Task Took Exactly 500 ms?

The timeout begins when the **caller enters this `get` call**, which may be after the task already spent time in a queue. Moreover, only the wait call itself is bounded; total latency also includes submission, request building, CPU scheduling, exception handling, and response writing. Java and the OS do not guarantee millisecond-exact thread wakeup timing.

For example: a caller submits a task, does other work for 2 seconds, and then calls `get(500, MILLISECONDS)`. It may receive the result immediately if the task has finished, or wait at most up to that timeout if the task is still unfinished. **This cannot be interpreted as "the task must finish within 500 ms from submission".**

## 3. Spring Framework: Submitting Tasks and Waiting with a Limit

At the interface level, Spring provides:

- `TaskExecutor` for submitting `Runnable`.
- `AsyncTaskExecutor` for submitting `Runnable`/`Callable` and receiving a result handle per the current API.
- `ThreadPoolTaskExecutor` for configuring pool, queue, and lifecycle as a Spring bean.
- `@EnableAsync` and `@Async` so Spring routes method execution through an executor when calls pass through a proxy.

A Spring method:

```java
@Async("reportExecutor")
public CompletableFuture<String> createReport(String id) {
    return CompletableFuture.completedFuture("report:" + id);
}
```

The snippet above **only illustrates a method body**, assuming a Spring bean, `@EnableAsync`, and an executor named `reportExecutor` already exist. When the Spring proxy handles `@Async`, the method body typically executes on the executor; the caller receives a `CompletableFuture<String>` and can wait via:

```java
String value = reportService.createReport("A")
    .get(2, TimeUnit.SECONDS);
```

If the caller calls `get` immediately, the caller may block up to the timeout while the worker continues processing. `@Async` does not make a `get` call non-blocking. If the caller does not want to block, consider callbacks/composition or an async contract on the calling layer.

**Proxy note:** `this.createReport(...)` inside the same bean typically does **not** pass through the Spring proxy in default mode, so the annotation may not trigger the executor. Calls must go through a Spring-managed bean reference, usually from another bean, and select the executor explicitly with `@Async("reportExecutor")` when the application has multiple pools.

## 4. Complete Java 17+ and Spring Example: Timeout Does Not Cancel the Task

The following example uses **Java 17+**, Maven, and **Spring Framework 6.2.12**. It requires neither Spring Boot nor an HTTP server. We use `CountDownLatch` to hold the worker at an intentional wait point, guaranteeing the caller hits `TimeoutException`; afterward the caller opens the latch and retrieves the result **from the same future**. That avoids relying on `Thread.sleep` or flaky millisecond comparisons.

Structure:

```text
spring-timed-get-demo/
├── pom.xml
└── src/main/java/demo/TimedGetDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-timed-get-demo</artifactId>
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
                    <mainClass>demo.TimedGetDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/TimedGetDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class TimedGetDemo {
    public static class Gates {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
    }

    public static class ReportService {
        private final Gates gates;

        public ReportService(Gates gates) {
            this.gates = gates;
        }

        @Async("reportExecutor")
        public CompletableFuture<String> createReport(String id) {
            gates.started.countDown();

            try {
                gates.release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }

            return CompletableFuture.completedFuture("report:" + id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean
        public ReportService reportService(Gates gates) {
            return new ReportService(gates);
        }

        @Bean("reportExecutor")
        public ThreadPoolTaskExecutor reportExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("report-");
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Gates gates = context.getBean(Gates.class);
            ReportService service = context.getBean(ReportService.class);

            CompletableFuture<String> future = service.createReport("A");

            try {
                if (!gates.started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker did not start");
                }

                boolean timeoutObserved = false;
                try {
                    future.get(100, TimeUnit.MILLISECONDS);
                } catch (TimeoutException expected) {
                    timeoutObserved = true;
                }

                System.out.println("timeoutObserved=" + timeoutObserved);
                System.out.println("doneBeforeRelease=" + future.isDone());
            } finally {
                // Important: do not leave the worker waiting forever if main fails.
                gates.release.countDown();
            }

            String result = future.get(5, TimeUnit.SECONDS);
            System.out.println("result=" + result);
            System.out.println("doneAfterRelease=" + future.isDone());
        }
    }
}
```

Run from the `spring-timed-get-demo` directory:

```bash
mvn -q compile exec:java
```

Four lines printed by the program during normal execution:

```text
timeoutObserved=true
doneBeforeRelease=false
result=report:A
doneAfterRelease=true
```

### Step-by-Step Analysis

1. The Spring context creates `reportExecutor`, a `ThreadPoolTaskExecutor` with only one worker in this example. `@EnableAsync` registers `@Async` processing.
2. `context.getBean(ReportService.class)` retrieves the bean via Spring. `service.createReport("A")` passes through the proxy; Spring submits the work to `reportExecutor` and returns a `CompletableFuture<String>` to the caller.
3. The worker enters `createReport`, decrements `started` to 0, and waits on `release`. Main proceeds only after `started.await(...)` confirms the worker has genuinely started, so it does not rely on scheduling luck.
4. Main calls `future.get(100, TimeUnit.MILLISECONDS)` while the worker **cannot finish** because `release` is not yet opened. This wait expires and throws `TimeoutException`; main prints `timeoutObserved=true`.
5. Right before opening the gate, the worker is still waiting. The Future is incomplete, so `doneBeforeRelease=false`. **The timeout did not cancel the future, did not open the gate, and did not kill the worker.**
6. The `finally` block opens the gate; the worker creates `CompletableFuture.completedFuture("report:A")` and Spring completes the future returned to the caller.
7. Main calls `future.get(5, TimeUnit.SECONDS)` **a second time on the exact same future**, receiving `report:A`. Once `get` returns the value, the future is complete, so `doneAfterRelease=true`.

If `started.await` expires or the thread is interrupted, the example throws intentionally and still opens the gate in `finally`. An environment error or executor failure could prevent printing these lines; the output describes a normal run.

### Why Is This Valid Evidence?

- `CountDownLatch` creates a coordination relationship: the caller waits on the future only after the worker reaches the checkpoint.
- The worker cannot finish computing and return the result before main opens `release` (barring external interruption).
- Timing out `get(100, MILLISECONDS)` only affects **main**'s wait behavior, without changing the task's completion state.
- The subsequent `get(5, SECONDS)` proves the same future can still deliver the result after an earlier timeout.

In real applications, do not use latches to simulate I/O or hold workers long-term. Choose appropriate client timeouts, size thread pools properly, and bound the number of running/waiting tasks.

## 5. Handling Exceptions Separately

The following pattern applies when you already have `Future<Result> future`. This is **illustrative code inside a method**, requiring `Result` and `fallback()` definitions per your application; it is not a standalone program:

```java
try {
    Result result = future.get(2, TimeUnit.SECONDS);
    return result;
} catch (TimeoutException ex) {
    // Caller exhausted wait budget. Task may still be running.
    recordTimeout(ex);
    return fallback();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // preserve caller stop request
    throw new IllegalStateException("Interrupted while waiting", ex);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause(); // actual error from the task
    throw new IllegalStateException("Task failed", cause);
} catch (CancellationException ex) {
    throw new IllegalStateException("Task was cancelled", ex);
}
```

`recordTimeout(...)`, `fallback()`, and `Result` are business components you implement; if no fallback is needed, a timeout can be translated into a controlled error. `CancellationException` is unchecked so it is not in `Future.get`'s `throws` list, yet it should still be accounted for if the application permits cancelling tasks. The `catch` blocks above do not cover executor submission failures occurring before a future is returned (such as Spring's `TaskRejectedException`).

### TimeoutException: The Waiter Ran Out of Time

Never assume a timeout means:

- The task never started. It may be sitting in a queue or already running.
- The task died or was cancelled. The Future is usually **still pending**.
- The remote server stopped processing the request. An already-sent HTTP call may still be running.
- It is safe to retry immediately. The old task may still write to the database after the caller returned a fallback.

On timeout, explicitly choose a strategy: let it finish in the background and store the result; return an error/fallback while the task keeps running; or attempt to cancel the task and bound resources. If the task has side effects, design idempotency and define how late results are handled.

### ExecutionException: The Task Failed

A task throwing `IllegalStateException` can cause `future.get(...)` to throw `ExecutionException` wrapping the real error. Inspect `ex.getCause()`, and do not confuse it with a timeout. When a `CompletableFuture` completes exceptionally, `get` also delivers the error via `ExecutionException`, whereas `join` typically throws `CompletionException` (unchecked).

### InterruptedException: The Waiting Thread Was Requested to Stop

If the caller thread is interrupted during `get`, Java may throw `InterruptedException`; the interrupted status is usually cleared when the exception is thrown. If not propagating the exception upward per contract, restore it via:

```java
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return; // or exit the method per the caller's contract
}
```

This is a snippet, not standalone. Do not swallow interrupts and continue an infinite wait loop. Also distinguish **caller interrupted** from **worker interrupted**: the two threads have distinct lifecycles and semantics.

### CancellationException: The Task/Future Was Cancelled

A cancelled future can cause `get(...)` to throw `CancellationException`. `isDone()` is still `true` because cancellation is also a terminal state of the future. If cancellation came from a deadline or user action, record the cancelled state explicitly.

## 6. `get(timeout)` Is Not `cancel()`

Two distinct operations:

| Operation | Primary effect | What must not be inferred |
| --- | --- | --- |
| `get(200, MILLISECONDS)` | Caller waits at most the specified timeout for that retrieval call. | Does not stop the task, interrupt the worker, or roll back. |
| `future.cancel(false)` | Attempts to cancel the future; with some implementations can prevent a not-yet-started task from running. | Does not force an already-running task to stop immediately. |
| `future.cancel(true)` | Attempts to cancel and may request interrupting the worker if supported by the implementation. | Does not guarantee the thread stops, I/O stops, or side effects roll back. |
| `future.isCancelled()` | Observes the future's cancelled status. | Does not prove external resources are clean. |

For example, Java's `ExecutorService.submit(Callable)` typically returns a `FutureTask` capable of attempting to interrupt the worker if `cancel(true)` succeeds. However, per the JDK contract, `CompletableFuture.cancel(true)` does not use `mayInterruptIfRunning` to control execution: completing the future in a cancelled state **does not guarantee interrupting background work**. A future received through Spring `@Async` also has a proxy/adaptation layer, so never build a system on the assumption that cancel always interrupts a specific thread.

If choosing to cancel after a timeout:

```java
try {
    return future.get(500, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    boolean requested = future.cancel(true);
    // Record status and handle side effects that may have already occurred.
    throw new IllegalStateException(
        "Timed out; cancel requested=" + requested, ex);
}
```

This is a snippet inside a method with an appropriate return type, not a standalone program. **`cancel(true)` is a best-effort request**, not a substitute for client-side request timeouts, transaction design, idempotency, or job status checks.

For high-value business workflows, sometimes letting the work continue in the background and returning `202 Accepted` with a job ID makes more sense than auto-cancelling, provided durable job status exists for the caller to poll. Conversely, work that only serves the current request should often stop cooperatively once the caller no longer needs the result.

## 7. Three Types of Timeouts Not to Conflate

### A. Caller Result Wait Timeout

```java
String value = future.get(300, TimeUnit.MILLISECONDS);
```

Bounds **a single result retrieval** on the caller. The task may have spent time in a queue beforehand, and may continue running after the caller times out.

### B. Internal Worker I/O Timeout

For instance, a blocking HTTP client may need a connect timeout and a response/read timeout; a database query may need a query timeout or an appropriate transaction timeout. If I/O can hang indefinitely, `future.get(300, MILLISECONDS)` only frees the caller from **that wait**; the worker remains occupied, saturating the pool.

Configure timeouts on **the actual blocking resource**, while bounding workers, queues, connections, and retries.

### C. Overall Request or Workflow Deadline

Suppose an API has a total budget of 1 second, yet must submit 3 tasks and collect each result. Calling `future.get(1, SECONDS)` sequentially three times could wait nearly 3 seconds, excluding submission, queuing, and other code.

When a **shared deadline** is required, record the start point with a monotonic clock (`System.nanoTime()`), compute remaining time before each wait, and pass that remainder. Do not reset the full timeout at every step. If the deadline has already passed, return an error or fallback instead of accidentally extending the budget.

Illustrative pattern in a method with `List<Future<String>> futures`:

```java
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(800);
long deadlineNanos = System.nanoTime() + budgetNanos;

List<String> results = new ArrayList<>();
for (Future<String> future : futures) {
    long remainingNanos = deadlineNanos - System.nanoTime();
    if (remainingNanos <= 0) {
        throw new TimeoutException("Overall deadline exceeded");
    }
    results.add(future.get(remainingNanos, TimeUnit.NANOSECONDS));
}
```

This pattern only illustrates a **shared wait budget**; it requires imports for `List`, `ArrayList`, `Future`, `TimeUnit`, `TimeoutException` and handling of checked exceptions. If the deadline must cover setup/submission time as well, compute `deadlineNanos` **before** those operations. The deadline window in this example is small relative to `nanoTime` wrap-around limits; for huge durations, handle potential overflow. After expiration, incomplete futures may still keep running.

`System.nanoTime()` measures elapsed intervals and is better suited than `System.currentTimeMillis()` for internal deadlines because wall-clock time can be adjusted. Deadlines propagated across distributed systems require clear contracts on time zones, clock skew, and expiration instants.

## 8. What Other Options Does `CompletableFuture` Offer?

`CompletableFuture<T>` implements `Future<T>`, so it has `get(timeout, unit)`, while also supporting composition:

| API | Behavior | Effect on the future |
| --- | --- | --- |
| `future.get(timeout, unit)` | Caller waits with a bound and gets the result or throws. | Does not proactively complete/cancel the future on expiration. |
| `future.get()` | Caller waits without a specific timeout. | Does not proactively cancel. |
| `future.join()` | Caller waits like unbounded `get()`, but throws unchecked exceptions like `CompletionException`. | Has no timeout parameter. |
| `future.orTimeout(timeout, unit)` | Schedules completing the future **with `TimeoutException`** if still incomplete when the duration expires. | Mutates the completion state of that `CompletableFuture` itself and returns the same future; the background task may still run. |
| `future.completeOnTimeout(value, timeout, unit)` | Schedules completing with a fallback value if still pending when expired. | Also mutates that future's completion; does not automatically stop the worker. |
| `future.thenApply(...)` | Transforms the value after completion. | Creates a dependent stage, avoiding direct caller blocking. |
| `future.whenComplete(...)` | Observes success or error. | Useful for logging/metrics; does not create a cancellation mechanism. |

Example:

```java
CompletableFuture<String> result = service.createReport("B")
    .orTimeout(2, TimeUnit.SECONDS);
```

This is a snippet using `ReportService` from the main example, not standalone; `orTimeout` can cause the future to finish with a timeout error, making a later `get` throw `ExecutionException` with cause `TimeoutException`, whereas `join` typically throws `CompletionException`. Timeout completion may occur **before** the real worker method finishes; completing the future does not mean all threads have been freed.

**Choose the API by intent:** `get(timeout)` fits when *one specific caller* may only wait so long; `orTimeout` fits when the completion stage itself should enforce a timeout policy. If one future is shared by multiple consumers, calling `orTimeout` or `completeOnTimeout` on it alters the outcome seen by every consumer. To bound one branch while preserving the original future, design a separate stage/adapter with its own contract and account for side effects.

## 9. Practical Issues in Spring MVC and Background Jobs

A Servlet controller calling:

```java
String report = reportService.createReport("X")
    .get(500, TimeUnit.MILLISECONDS);
```

is **blocking the request thread** for up to the wait limit. Under overload, hundreds of HTTP requests waiting concurrently can tie up many servlet threads; even though tasks run on another executor, HTTP capacity still suffers. The snippet above belongs inside a controller with exception handling, not a standalone program.

If you want Spring MVC to manage the asynchronous HTTP request lifecycle, you can use supported return types such as `Callable<T>`, `DeferredResult<T>`, or `CompletionStage<T>`/`CompletableFuture<T>` depending on version and configuration. Then the async HTTP request timeout is a **separate policy layer**; you must consider background task state, response timeouts, and client disconnects. Returning a `Future` to MVC also does not make I/O inside the worker non-blocking.

For background jobs, the caller may not need the result immediately. Using timed `Future.get` merely to return a provisional response can lead to **late results**. If the job produces side effects, persist a `jobId`, status, expiration timestamp, idempotency key, and result storage location. A thread pool and queue in RAM do not ensure a job survives a restart.

Workflow example:

```text
POST /reports
   -> validate idempotency key
   -> persist job record (PENDING)
   -> dispatch task/queue
   -> return job ID (202 Accepted)

GET /reports/{jobId}
   -> read status PENDING/RUNNING/SUCCEEDED/FAILED
```

This is an **architectural diagram**, not API code implemented in the sample. It illustrates an alternative when the business does not require the caller to wait synchronously for the result.

## 10. Designing Sensible Timeouts and Avoiding Common Mistakes

### Budget Across the Entire Path

When there is a request deadline, allocate time across queue wait, connect, read, business processing, serialization, and overhead. For instance, an HTTP client setting a 1-second deadline while the server calls `future.get(5, SECONDS)` can keep the server waiting after the client has given up; set matching limits at each layer.

Do not set `get(timeout)` longer than all other timeout layers without good reason. Conversely, an overly short timeout can cause unnecessary fallbacks or retries while the worker is about to finish; measure p95/p99 and false-timeout rates to tune it.

### Avoid Looping Timeouts Into an Infinite Wait

Bad pattern:

```java
while (true) {
    try {
        return future.get(100, TimeUnit.MILLISECONDS);
    } catch (TimeoutException ignored) {
        // Infinite loop: grants another 100 ms of waiting each iteration.
    }
}
```

Without an overall deadline or stopping condition, the caller can wait forever even though each `get` has a timeout. Periodic polling is only worthwhile for a specific purpose like progress updates and must have an overall deadline.

### Do Not Substitute Caller Timeouts for Resource Controls

If a worker hangs because an HTTP client lacks a timeout, the caller giving up does not free the worker. The system can still fill up the pool and queue. Set executor bounds, I/O timeouts, budgeted retries, and monitor downstream health. With `CallerRunsPolicy`, under saturation tasks can run directly on the caller, so **even submission itself** can block before a future is returned.

### Do Not Discard Exceptions and Interrupts

Catching generic `Exception` and returning `null` hides whether the cause was a timeout, cancellation, or business failure. In particular, `InterruptedException` usually needs to be propagated or have the interrupt flag restored so higher-level shutdown/cancellation still works. Choosing a fallback must also signify "no timely result", rather than treating it as valid success data to write to the database.

### Do Not Treat `isDone()` as "Task Succeeded"

`future.isDone()` returns `true` even on cancellation or failure. Retrieve the result per contract and inspect the corresponding exceptions and states. `isCancelled()` also does not confirm the task stopped all side effects.

### Do Not Rely on `Thread.sleep` to Prove Timeouts

If an example used `Thread.sleep(200)` and `get(100, MILLISECONDS)`, scheduler delays or host resource contention could make observations flaky. The example in this lesson uses `CountDownLatch` to demonstrate deterministically. In production tests, prefer test doubles, controllable clocks, or latches/phasers over lucky timing.

## 11. Checklist When Reviewing `get(timeout)` Code in a Project

1. **Where does the Future come from?** `ExecutorService.submit`, Spring `AsyncTaskExecutor`, `@Async` proxy, or another API? Could the executor run synchronously, and what is its rejection policy?
2. **Who is calling `get`?** A Servlet thread, `main`, a pool worker, or a callback? Is it allowed to block, and for how long?
3. **When does the timer start?** Measured from calling `get` or from the overall request deadline? Has queue time already elapsed beforehand?
4. **If the wait expires, where does the task go?** Does it keep running, receive a best-effort cancel, write a late result, or leave side effects?
5. **Are failures differentiated?** Do timeout, task failure, interrupt, cancellation, and submission rejection each have clear handling paths?
6. **Does real I/O have timeouts?** Could HTTP/database/locks hold the worker even after the caller stops waiting?
7. **Are there multiple sequential steps?** Use a shared deadline budget to avoid stacking multiple `get(timeout)` waits.
8. **Can caller blocking be avoided?** On HTTP paths or long pipelines, consider composition, Spring MVC async, job status, or durable queues instead of blocking directly.
9. **Is observability in place?** Measure queue wait, task duration, timeout counts, exception causes, cancellations, and occupied workers; logs need correlation IDs and cleanup when crossing threads.
10. **Is correctness preserved when results arrive late?** An older task may still update data after a caller retries; use idempotency, versioning/transactions, and duplicate-resolution policies.

## 12. Self-Check Questions

**Question 1.** `future.get(300, MILLISECONDS)` throws `TimeoutException`. Has the Future necessarily transitioned to cancelled?

**Answer:** No. That is **the caller's** wait timeout expiring. The Future may still be pending and the worker still running. You can call `get` again later or apply a separate cancellation strategy.

**Question 2.** A task was submitted 2 seconds ago, and the caller now calls `get(100, MILLISECONDS)`. Does this set the task's deadline at submit time + 100 ms?

**Answer:** No. The limit applies from when this `get` call executes; if the task has already finished, `get` returns immediately.

**Question 3.** Why does calling `future.get(1, SECONDS)` three times sequentially not create a shared 1-second deadline?

**Answer:** Each wait has its own budget; wait durations can add up. You must store a shared deadline using a monotonic clock and pass only the remaining time to subsequent `get` calls.

**Question 4.** `get` throws `ExecutionException`. Is this a timeout?

**Answer:** No. The task completed with an error; inspect `ex.getCause()`. A `get` timeout has its own exception, `TimeoutException`.

**Question 5.** The caller is interrupted while waiting on `Future.get`. Can it catch `InterruptedException` and keep waiting indefinitely?

**Answer:** It should not. Propagate the signal upward or restore the interrupt flag and exit per contract so shutdown/cancellation is not ignored.

**Question 6.** Does `future.cancel(true)` guarantee the worker stops and the remote HTTP request is cancelled?

**Answer:** No. Interrupt capability depends on the future/executor type and task cooperation; `CompletableFuture.cancel(true)` does not necessarily interrupt the computation.

**Question 7.** In the demo, why did the second `get(5, SECONDS)` return `report:A` after the first timed out?

**Answer:** The first timeout did not cancel the future. Once main opened the gate, the worker finished and Spring completed the caller's handle, so the subsequent `get` received the result.

**Question 8.** A Spring MVC controller calls an `@Async` service and immediately calls `get(500, MILLISECONDS)`. Is the controller thread freed to serve other requests while waiting?

**Answer:** No. The controller thread itself is blocked by `get`; to free it, use MVC's async request contract or a different API design.

### Takeaway

`Future.get(timeout, unit)` is **a bound on a single caller wait for a result**, not a tool that automatically stops a task. Proper design must clarify **how long the caller may wait, how long the worker may run, when to cancel, when late results are acceptable, and how errors/side effects are handled**. In Spring, always account for the executor, `@Async` proxy, HTTP lifecycle, and underlying resources.

### Official References

- [Java 17 — Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout, unit)`, states, and exceptions.
- [Java 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `orTimeout`, `completeOnTimeout`, `join`, `cancel`.
- [Java 17 — TimeUnit API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): time units and conversions.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor`, `@EnableAsync`, `@Async`, and executor qualification.
