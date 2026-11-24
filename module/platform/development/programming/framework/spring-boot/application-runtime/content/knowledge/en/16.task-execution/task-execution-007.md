# Thread Interruption Propagation and Designing Cancellable Tasks

## 1. Goal: canceling a task without corrupting system state

In Spring Boot, a task may run on an HTTP handler thread, `ApplicationRunner`, `@Async`, `@Scheduled`, a background job executor, or a message consumer. When a user cancels a job, a request times out, or the application shuts down, the work must terminate **in a controlled way**, not merely stop printing logs.

Questions that must be answered:

- Who owns the task, and who is authorized to request cancellation?
- How does the cancellation signal reach the task?
- Does a task running a CPU loop, `sleep`, queue wait, network I/O, or database call actually respond?
- While writing to a database or acknowledging a message, at what points can the task safely stop?
- Can the coordinator distinguish **cancellation requested** from **actually terminated**?
- Does Spring context shutdown allow enough time to drain, clean up, and close dependencies?

In Java, **interruption is a cooperative request**. `Thread.interrupt()` is not a forced thread-kill command. Tasks must respond to the interrupt flag or `InterruptedException`, while also designing timeouts, cleanup, and recovery of unfinished work. For I/O that does not support interruption, use the library's cancellation API or dedicated deadlines.

This content applies to **Java 17+**, Spring Framework 6.x, and Spring Boot 3.3.x. The runnable example uses Spring Boot 3.3.13, Java 17, Maven, and `spring-boot-starter`.

## 2. Thread interruption is a signal, not an instant stop operation

Every `Thread` in Java has an **interrupted status**. One thread can request another thread to interrupt:

```java
worker.interrupt();
```

`worker` is a `Thread` reference assumed already created; this is an illustrative statement.

On the receiving thread, you can inspect:

```java
boolean requested = Thread.currentThread().isInterrupted();
```

When a worker is blocked inside interrupt-aware APIs such as `Thread.sleep`, `Object.wait`, `Thread.join`, or `BlockingQueue.take`, the API typically throws `InterruptedException`. However, if a worker runs a CPU loop without checking the flag, it can keep running indefinitely even after being interrupted.

| API / scenario | Meaning |
| --- | --- |
| `someThread.interrupt()` | Requests interrupting `someThread`; **does not guarantee the task stopped** |
| `someThread.isInterrupted()` | Reads the interrupted status of the target thread, **without clearing the flag** |
| `Thread.currentThread().isInterrupted()` | Reads the current thread's flag without clearing |
| `Thread.interrupted()` | Static method: reads current thread's flag **and clears the flag** |
| `Thread.sleep(...)` when interrupted | Throws `InterruptedException`, typically clearing the flag when thrown |
| CPU loop not checking the flag | Can ignore interruption requests |
| Blocking HTTP/JDBC call | Behavior depends on client/driver; must configure explicit timeouts/cancellation |
| `Thread.stop()` | Deprecated as unsafe; **never use** |

### 2.1. `isInterrupted()` and `Thread.interrupted()` are not interchangeable

```java
Thread thread = Thread.currentThread();

boolean a = thread.isInterrupted(); // Reads without resetting.
boolean b = Thread.interrupted();    // Reads and resets the current flag.
```

Suppose the flag is already `true`. After `isInterrupted()`, subsequent code still observes the interrupt; after `Thread.interrupted()`, the flag has been cleared. Therefore, loops wanting to **observe** cancellation requests typically use:

```java
while (!Thread.currentThread().isInterrupted()) {
    processNextChunk();
}
```

This is an illustrative snippet requiring a real `processNextChunk()` and reasonably short iterations. If the handler blocks inside an API that does not respond to interrupts, checking the flag at the top of the loop **is not enough** to bound cancellation latency.

### 2.2. Why does `InterruptedException` usually clear the flag?

`InterruptedException` already serves as a typed signal telling callers the thread was asked to interrupt while waiting. Many blocking APIs clear the interrupted status when throwing the exception. Consequently, if you catch the exception without propagating it, higher layers may no longer see the interrupt flag.

There are two main handling patterns:

1. **Propagate `InterruptedException` to the caller** when the method signature allows.
2. **Restore the flag via `Thread.currentThread().interrupt()` and exit the task** when checked exceptions cannot be declared.

Never catch it and silently continue as if the task completed normally.

## 3. Propagating interruption across methods

### 3.1. Propagating is simplest when the API allows it

```java
void waitForData() throws InterruptedException {
    Thread.sleep(1000L);
}

void processBatch() throws InterruptedException {
    waitForData();
    commitResult();
}
```

This is illustrative code; `commitResult()` must be implemented separately. If the thread is interrupted inside `waitForData()`, the exception propagates out of `processBatch()` and **does not execute** `commitResult()`.

The benefit is that the coordinating layer knows the task did not succeed. Never wrap the exception pointlessly or add a `catch` in a helper just to log and keep going.

### 3.2. Boundaries that cannot throw checked exceptions

`Runnable#run()` cannot declare `throws InterruptedException`. Restore the flag and exit:

```java
Runnable worker = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            Thread.sleep(1000L);
            processOneBatch();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        closeOwnedResources();
    }
};
```

`processOneBatch()` and `closeOwnedResources()` are assumed helper methods in the enclosing class. `finally` runs when the task exits, releasing resources **owned by the task**. If cleanup involves I/O, still enforce time limits and failure policies when cleanup fails.

If upper layers need a reason, at an appropriate boundary:

```java
try {
    performBlockingStartupStep();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Startup cancelled", e);
}
```

This is an illustrative snippet assuming `performBlockingStartupStep()` declares `throws InterruptedException`. That can fit mandatory startup steps, whereas in API requests or message workers, translate it into a domain cancellation state instead of treating every interrupt as a business error by default.

### 3.3. Anti-pattern: swallowing interruption

```java
try {
    Thread.sleep(1000L);
} catch (InterruptedException ignored) {
    System.out.println("still working");
}
continueProcessing();
```

`continueProcessing()` is an illustrative method. Here, the task ignores the cancellation signal; the interrupt flag may have been cleared by `sleep`. Consequences include prolonged shutdown or a job continuing to write data after the user canceled it.

Another anti-pattern:

```java
while (true) {
    try {
        Thread.sleep(1000L);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
```

The loop still has no exit path. Every subsequent iteration may immediately hit `InterruptedException`, causing a busy loop. **Restoring the flag must accompany a decision to exit the task**, or propagate the exception to a controlling layer.

### 3.4. `finally` does not replace transaction design

If an interrupt arrives mid-way through `read -> update database -> ack message`, in-memory cleanup does not automatically roll back committed database writes or redeliver messages. You need transaction boundaries, idempotency keys, checkpointing, and rules to ack only once results are durable.

Never log "success" when a task only processed partially before being canceled. Statuses `CANCELLED`, `TIMED_OUT`, `FAILED`, and `SUCCEEDED` must have clear business definitions.

## 4. Designing cancellable CPU-bound and I/O-bound tasks

### 4.1. CPU-bound: check between chunks

For large data processing:

```java
for (int i = 0; i < items.size(); i++) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    transform(items.get(i));
}
```

This is illustrative, requiring real `items` and `transform(...)`. If a single `transform` call takes tens of minutes, checking only before it still cannot ensure fast cancellation. Split work into bounded chunks with checkpoints and check at sensible intervals.

**Do not** check interruption after every addition in a tight compute loop if it creates needless overhead; choose check points matching cancellation latency requirements.

### 4.2. Blocking queues or condition waits

APIs like `BlockingQueue.take()` can throw `InterruptedException`; typically propagate it in worker methods or restore the flag and break inside `Runnable`.

Avoid `while (true) { queue.poll(); }` spinning continuously and burning CPU. When using `poll(timeout, unit)`, code can periodically inspect a cancellation token or shutdown flag while still reacting properly to interrupts.

### 4.3. External I/O may not respond to interrupts

There is no general guarantee that `Thread.interrupt()` immediately stops:

- An HTTP request waiting on a response.
- A JDBC query running on a database.
- A cloud SDK performing internal retries.
- File I/O or a library's native blocking call.
- A message broker connection without a deadline.

Check the specific client contract and configure connect/read timeouts, request cancellation APIs, SQL query timeouts, overall deadlines, and retry bounds. A thread may already be marked interrupted yet remain blocked in I/O until the socket times out.

Never substitute `Future.cancel(true)` for real timeouts and consider the problem solved.

### 4.4. Cancellation tokens when interruption is not enough

A cooperative application-level flag:

```java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean(false);

    public void cancel() {
        requested.set(true);
    }

    public boolean isCancellationRequested() {
        return requested.get();
    }
}
```

This is a standalone Java 17 file suitable for `CancellationToken.java`. Workers inspect the token between chunks. Tokens help pass cancellation requests across multiple methods or retain handles in a job registry. However, a token **does not wake up** a `sleep` or network call on its own; usually combine token + interrupt + I/O timeouts.

### 4.5. Overall deadline differs from per-call timeout

A task making four requests, each with a 20-second timeout plus retries, can exceed a 60-second budget. The deadline must cover I/O, retries, backoff, data processing, and cleanup within bounds.

For durations inside the same JVM, `System.nanoTime()` is a better source of elapsed time than wall-clock timestamps:

```java
long started = System.nanoTime();
long budget = TimeUnit.SECONDS.toNanos(30);

while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    long remaining = budget - (System.nanoTime() - started);
    if (remaining <= 0L) {
        throw new IllegalStateException("Job deadline exceeded");
    }
    processChunkWithin(remaining);
}
```

This is illustrative, requiring real `hasMoreWork()` and `processChunkWithin(...)`. In business APIs, choose appropriate domain exceptions/statuses rather than always throwing `IllegalStateException`. Enforce valid budget bounds and never pass negative durations to clients.

## 5. `Future.cancel(true)`: requests interruption, does not prove stopping

With `ExecutorService`:

```java
Future<?> future = executor.submit(() -> doWork());
boolean accepted = future.cancel(true);
```

Both `executor` and `doWork()` need definitions. `mayInterruptIfRunning=true` asks the implementation to try interrupting the thread running the task, if known.

| Task state when cancel is called | What can happen |
| --- | --- |
| Not yet started | Task is normally prevented from running |
| Running and interrupt-aware | Receives signal, exits via flag or exception |
| Running yet ignoring interrupts | `Future` may show cancelled while task body keeps running |
| Already completed | `cancel` normally does not alter the outcome |
| Other Executor implementations | Read actual contract; do not assume all executors behave identically |

**`future.isCancelled()` indicates Future state, not necessarily that the task's code finished its `finally` block.** If safely closing dependencies matters, await an explicit completion signal or executor termination.

### 5.1. `Future.get(timeout)` does not cancel the task automatically

```java
try {
    Object value = future.get(2, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException e) {
    future.cancel(true);
    throw e;
}
```

This is illustrative: `future` and `use` must exist; the enclosing method must declare/handle checked exceptions. `get(timeout)` only limits **how long the caller waits**. On `TimeoutException`, the worker may still be running; to stop it, explicitly request cancellation and make the task cooperate.

If the caller itself is interrupted during `get(...)`, consider canceling the child task and then propagating `InterruptedException` or restoring the flag at the proper boundary.

### 5.2. `CompletableFuture.cancel(true)` differs from `FutureTask`

A common pitfall when using async APIs:

```java
CompletableFuture<Void> result =
        CompletableFuture.runAsync(this::longRunningTask);
result.cancel(true);
```

The snippet assumes `longRunningTask()` exists. Per Javadoc, `CompletableFuture.cancel(boolean)` does not use interruption to control execution; the `mayInterruptIfRunning` parameter **has no effect** in this implementation. The Future can transition to cancelled while `longRunningTask` keeps working.

Likewise, `CompletableFuture.orTimeout(...)` can complete the future exceptionally on timeout without guaranteeing the underlying body stopped. If real cancellation is required, use an executor-owned `Future` handle, a cancellation token, or the library's abort API, and verify completion.

## 6. Shutting down an executor: soft first, hard later

Distinguish three operations:

- `ExecutorService.shutdown()`: stops accepting new tasks and lets submitted tasks proceed per executor policy; **does not actively interrupt running tasks**.
- `ExecutorService.shutdownNow()`: attempts to stop running tasks (typically via interrupt) and returns a list of queued tasks that never started; **does not guarantee** all tasks have stopped.
- `awaitTermination(timeout, unit)`: waits for true executor termination within a budget, returning `false` if unfinished; can be interrupted while waiting.

Standard pattern:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Tasks still running");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This is an illustrative snippet inside a method with `ExecutorService executor` and `TimeUnit` imported. The 10+5 second durations are examples that must fit your real shutdown budget. `shutdownNow()` is not a kill switch; if tasks ignore interrupts, log, retry, or recover when the process restarts.

### 6.1. Coordinating with dependent resources

A safe sequence is typically:

```text
Stop accepting new jobs
        ↓
Let in-flight tasks drain within deadline
        ↓
Request cancellation for tasks exceeding deadline
        ↓
Wait for task stop confirmation / record unfinished tasks
        ↓
Close database/HTTP client/message transport still used by tasks
```

If you close connection pools before workers finish writing results, even an interrupted task can fail during cleanup or lose acknowledgments. That is why applications need lifecycle coordination rather than arbitrarily calling `shutdownNow()` from an ad-hoc shutdown hook.

## 7. Complete example: Spring Boot 3.3 + Java 17 task cancellation with confirmation

This example creates an `ExecutorService` as a Spring bean and uses an `ApplicationRunner` to submit a task. The task signals start via `CountDownLatch`, then waits inside `Thread.sleep`. The caller calls `Future.cancel(true)` and **awaits a separate finish latch** to confirm the task body exited `finally`.

No HTTP server is needed. On this startup path, the demo completes before letting `SpringApplication.run()` return.

### 7.1. Project structure

```text
cancellable-worker-demo/
├── pom.xml
└── src/main/java/com/example/cancel/
    └── CancellableWorkerApplication.java
```

### 7.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>cancellable-worker-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 7.3. File `CancellableWorkerApplication.java`

```java
package com.example.cancel;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CancellableWorkerApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(CancellableWorkerApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner is invoked by Boot and finishes before run() returns.
        }
    }

    @Bean(destroyMethod = "shutdown")
    ExecutorService workerPool() {
        return Executors.newSingleThreadExecutor();
    }

    @Bean
    ApplicationRunner demonstrateCancellation(ExecutorService pool) {
        return args -> {
            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch finished = new CountDownLatch(1);

            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    while (!Thread.currentThread().isInterrupted()) {
                        Thread.sleep(60_000L);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                future.cancel(true);
                throw new IllegalStateException("Task did not start");
            }
            System.out.println("task-started");

            boolean accepted = future.cancel(true);
            System.out.println("cancel-requested=" + accepted);

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not stop");
            }
            System.out.println("task-stopped");
            System.out.println("future-cancelled=" + future.isCancelled());
        };
    }
}
```

### 7.4. Run

In the directory containing `pom.xml`:

```bash
mvn package
java -jar target/cancellable-worker-demo-0.0.1-SNAPSHOT.jar
```

If Maven Wrapper was generated:

```bash
./mvnw package
```

Windows PowerShell with wrapper:

```powershell
.\mvnw.cmd package
```

The example requires JDK 17+, Maven, and Spring Boot dependencies on the classpath; you cannot use bare `javac` without configuring libraries.

### 7.5. Expected output

Lines **explicitly printed by the demo code** in order:

```text
task-started
cancel-requested=true
task-stopped
future-cancelled=true
```

Boot/build tool logs may interleave. This order is protected by two latches rather than sleeping and guessing when the worker started.

Explanation:

1. The task calls `started.countDown()` on entry. The caller awaits the latch before printing `task-started`.
2. The task is inside the `sleep` loop, so the caller can issue `future.cancel(true)` and attempt to interrupt the worker.
3. When the worker receives the interrupt inside `Thread.sleep`, it throws `InterruptedException`; the code restores interrupted status and runs `finally`.
4. `finished.countDown()` marks that the task body reached its designed exit point. The caller awaits this latch before printing `task-stopped`.
5. `future.isCancelled()` reflects Future state, not sole proof that the task stopped.

If the worker ignored interrupts, the caller would time out on `finished.await(...)` and fail the demo instead of claiming success. Real systems must record unstopped jobs and apply fallbacks.

### 7.6. Role of the Spring context

The `ExecutorService` bean is owned by Spring with an explicit `destroyMethod="shutdown"`. When the context closes, the executor stops accepting new work. However, canceling **a specific job** remains the responsibility of the component holding its `Future`.

Never spawn ad-hoc executors per request and leave them unclosed. In production, use lifecycle-managed executors with bounded threads/queues and a registry holding job handles for cancellation and cleanup.

## 8. Applying to `ThreadPoolTaskExecutor`, `@Async`, and schedulers

### 8.1. Managed `ThreadPoolTaskExecutor`

Spring Framework provides `ThreadPoolTaskExecutor`. An illustrative configuration:

```java
@Bean(name = "businessExecutor")
ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("business-");
    executor.setWaitForTasksToCompleteOnShutdown(false);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
```

This is a method snippet inside a `@Configuration` class; import `@Bean` and `ThreadPoolTaskExecutor`. `setAwaitTerminationSeconds(10)` is a shutdown wait budget, **not a per-task timeout**. Exact task-stopping details depend on lifecycle processors and executor policies, with no guarantee every task is interrupted instantly.

Spring Boot 3.3 can auto-configure an executor when no other `Executor` bean exists. Example properties for the auto-configured executor:

```properties
spring.task.execution.pool.core-size=2
spring.task.execution.pool.max-size=4
spring.task.execution.pool.queue-capacity=20
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
```

Auto-configuration properties **do not automatically apply** to custom executors created manually by the application. When `await-termination=true`, tasks may be allowed to finish naturally; choose policies based on job drain needs rather than because a property name contains `await`.

### 8.2. `@Async` may not provide the cancellation path you expect

To use `@Async`, the application must enable async support (`@EnableAsync` on an appropriate config) and invoke methods through a Spring proxy. Self-invocation inside the same bean normally bypasses the proxy and fails to dispatch asynchronously.

Illustrative example:

```java
@Service
class ReportService {

    @Async("businessExecutor")
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture("done");
    }
}
```

Requires imports for `@Service`, `@Async`, and `CompletableFuture`, plus a `businessExecutor` bean. This illustrates the return type, not a long-running background job.

When callers receive `CompletableFuture`, **do not assume `cancel(true)` interrupts the worker**. For jobs that must stop mid-execution, choose `ExecutorService.submit(...)`/`ThreadPoolTaskExecutor.submit(...)` to obtain a contract-compliant `Future<?>`, or manage a dedicated cancellation token/abort API.

### 8.3. `@Scheduled` also needs cooperation

A scheduled job may have already started before shutdown. The scheduler stopping new triggers does not mean the currently executing job body stopped. Long batch jobs must check interrupts/tokens, enforce I/O timeouts, checkpoint, and handle replay.

Spring Boot `spring.task.scheduling.*` policies are separate from `spring.task.execution.*`; tuning one group will not affect the other.

### 8.4. `ApplicationRunner` and readiness

Runners execute after context refresh and before `ApplicationReadyEvent`. If a runner waits indefinitely on a task, the web server may already have bound its port while the application is not yet ready. For mandatory startup steps, enforce deadlines and propagate errors so Boot does not falsely declare readiness.

If a runner only submits a background task and returns, Boot can announce readiness to accept traffic even though that task is still running. When background work must finish before serving traffic, use a custom readiness indicator or keep that step synchronous in the runner.

### 8.5. `SmartLifecycle.stop(Runnable)` must signal at the right time

For background services running throughout the lifecycle, `SmartLifecycle` is one way to manage start/stop. `stop(Runnable callback)` must:

1. Stop accepting new tasks.
2. Request draining or canceling remaining running tasks.
3. Wait for completion within budget.
4. Invoke `callback.run()` once stopping has actually completed per contract.

Do not invoke the callback immediately after `Future.cancel(true)` if tasks might still be using datasources/transports. `spring.lifecycle.timeout-per-shutdown-phase` is only a per-phase wait budget, **not a killer for uncooperative tasks**. When shutdown involves dependencies, workers must stop before the resources they still use.

## 9. When the application shuts down or a client cancels a request

### 9.1. HTTP client disconnect is not a global interrupt

A user closing their browser does not guarantee a job already submitted to a server executor gets interrupted. Depending on Spring MVC/WebFlux, async requests, reactive cancellation, and client libraries, the signal may or may not reach background work.

For long jobs, maintain a job ID, status registry, authorized cancel API, and handle cleanup when the job finishes. Never look up `Thread` by name to interrupt arbitrarily; that is not a safe ownership model.

### 9.2. Stop intake before canceling in-flight work

A resilient workflow transitions the instance out of receiving new traffic, stops consumers/schedulers, and then drains or cancels in-flight work. Finally, close connection pools and transports.

In Kubernetes, measure and align `terminationGracePeriodSeconds`, readiness/liveness, graceful shutdown, and Spring lifecycle timeouts. If a process is forcibly killed, Java callbacks are not guaranteed to run; message replay and idempotency remain essential.

### 9.3. Interruption alone cannot guarantee every task completed

If a process dies suddenly or a native I/O call never returns, Java interrupts cannot ensure distributed transactions completed. You must have durable state, retry/checkpointing, idempotency, and recovery policies on subsequent instances.

## 10. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Catching `InterruptedException` and ignoring it | Cancellation signal lost, work continues | Propagate or restore + exit |
| Calling `Thread.interrupted()` just to inspect | Accidentally clears interrupt flag | Use `isInterrupted()` |
| Calling `interrupt()` and assuming task stopped | Task may still be running | Await a separate completion signal |
| CPU task never checking the flag | Cancellation ignored | Check at chunk boundaries |
| I/O without timeouts | Shutdown can hang | Client timeouts / request cancellation |
| `Future.get(timeout)` times out without canceling | Worker keeps running in background | Decide cancellation and confirm stop |
| Treating `CompletableFuture.cancel(true)` as thread interrupt | Underlying work may continue | Cancellation token or executor-owned Future |
| Treating `shutdownNow()` as a forced kill | Tasks still hold resources | `awaitTermination`, deadlines, fallbacks |
| Runner loops infinitely | Boot never reaches `ApplicationReadyEvent` | Managed background lifecycle |
| `@Async` self-invocation | Method may run synchronously | Call through Spring proxy or explicit executor |
| Destroying datasource before workers stop | Workers fail mid-flush/ack | Lifecycle ordering and graceful drain |
| Restoring flag inside an infinite loop | Busy loop, stuck shutdown | Break/return/propagate |
| Canceling after partial commit | Retries may duplicate writes | Transaction boundaries and idempotency |

### 10.1. Never use `Thread.stop()`

`Thread.stop()` can halt a thread while holding locks or mutating state, breaking invariants of shared objects. It was deprecated because it is unsafe. Use cooperative cancellation alongside deadlines, timeouts, and resource lifecycle management.

### 10.2. Avoid retrying on every exception

Interrupted/cancelled is a control state, not a transient network error to retry automatically 10 times. When code needs to retry work after a restart, enforce durable state/idempotency at the orchestration layer rather than having a canceling worker immediately re-trigger itself inside `catch`.

### 10.3. Cancelled tasks may still require cleanup

Cancellation latency is the elapsed time from request until work actually leaves its critical section. If cleanup must flush buffers or release locks, observe cleanup duration and bound it explicitly; never measure latency only up to `future.isCancelled()` turning `true`.

## 11. Meaningful cancellation testing

A good test verifies both **cancellation was requested** and **the task truly terminated**.

### 11.1. Use latches instead of `Thread.sleep` in orchestration tests

Have the test worker call `started.countDown()` once running, and `finished.countDown()` inside `finally`. Have the test caller await `started`, invoke `future.cancel(true)`, await `finished` with a timeout, and verify cleanup. This avoids races from assuming a thread surely started after 100 ms.

### 11.2. Test exception paths and flag restoration

For helpers declaring `throws InterruptedException`, test that the caller receives the exception and skips subsequent business actions. For self-catching `Runnable`s, test that the task exits, cleanup runs, and no further batches execute.

### 11.3. Test uncooperative I/O

Stub a client simulating blocking or ignoring cancellation. Confirm the caller's deadline does not hang forever, failure policy is clear, and the system does not inadvertently close still-in-use resources. Never assume every driver reacts like `Thread.sleep()`.

### 11.4. Spring context integration tests

Create a context with real workers/executors, submit tasks, and close the context. Verify stop ordering, rejection of new jobs, appropriate wait durations, logging of unfinished tasks, and replay capability if shutdown is force-killed.

## 12. Pre-production design checklist

- [ ] Define the **owner** of each task and which APIs may request cancellation.
- [ ] Retain `Future`/cancellation token/job ID until the job ends, cleaning up handles timely.
- [ ] Split CPU loops into chunks to observe interruption.
- [ ] Propagate `InterruptedException` when possible; at other boundaries restore the flag and exit.
- [ ] Set connect/read/request timeouts and overall deadlines with bounded retries.
- [ ] Do not confuse `Future.cancel(true)` with confirmation that the task stopped.
- [ ] Do not confuse `CompletableFuture.cancel(true)` with worker interruption.
- [ ] Use completion signals when shutdown must wait for resources to be released.
- [ ] Handle rollback/checkpoint/idempotency for partial or partially committed work.
- [ ] Stop accepting new jobs before draining/canceling in-flight tasks.
- [ ] Keep dependencies alive until workers stop using them.
- [ ] Test timeouts, interrupts, cancel races, and forced process kills.
- [ ] Monitor canceled job counts, cancellation latency, timeouts, and workers failing to stop on time.

## 13. Official references

- [Java 17 `Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `isInterrupted`, `Thread.interrupted`, interruption during blocking.
- [Java 17 `Future` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `get`, cancellation status.
- [Java 17 `CompletableFuture` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel(boolean)` does not use interruption to control processing.
- [Java 17 `ExecutorService` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): configuring task executors and schedulers.
- [Spring Framework 6.1 — `ThreadPoolTaskExecutor`](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): managing thread pools and shutdown.
- [Spring Framework — `SmartLifecycle`](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/SmartLifecycle.html): stop callbacks and lifecycle phases.

## 14. Key takeaways

**Interruption is a cooperative request signal, not a thread-kill button.** Tasks must check the flag, propagate `InterruptedException`, or restore the flag and exit at appropriate boundaries.

`Future.cancel(true)` is an interruption attempt, not proof that the worker has stopped. With `CompletableFuture`, passing `true` has no effect on interrupting underlying work. `Future.get(timeout)` only bounds waiting time, and `shutdownNow()` is likewise only a cancellation attempt.

A genuinely cancellable task needs a **cancellation signal**, **deadlines/I/O timeouts**, **completion acknowledgment**, **ordered cleanup**, and **durable state for safe retries**. In Spring Boot, tie those requirements to executor ownership, readiness, and shutdown lifecycle rather than simply adding an `interrupt()` call.