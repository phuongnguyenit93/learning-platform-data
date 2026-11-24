# Distinguishing Submitted Tasks from Completed Tasks

## 1. The problem: does a successful submit call mean the work is done?

In a Spring Boot application, many places launch work off the current calling thread: `Executor.execute(...)`, `ExecutorService.submit(...)`, `CompletableFuture.supplyAsync(...)`, `@Async` methods, schedulers, or an `ApplicationRunner` submitting tasks to a thread pool. When the submission call returns normally, it is tempting to log "processing finished" or publish a "ready" status. **This is a common reasoning error.**

At minimum, distinguish five milestones:

1. **Submitted / accepted:** the execution request was handed to the executor and was not immediately rejected at call time. The task may sit in a queue.
2. **Started / running:** a thread actually began executing the task body.
3. **Completed:** the task reached a terminal state per the tracking object's contract. This may be **success, failure, or cancellation**.
4. **Succeeded:** the body returned a valid result or the desired side effect was confirmed per contract.
5. **Observed / acknowledged:** the caller received/inspected the result, updated business state, or the target system confirmed a durable commit if external systems are involved.

**"Submitted" does not mean "started". "Completed" does not mean "succeeded". And "Future is done" does not by itself prove an external system committed data.**

This lesson is set in the context of **Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+**. We will use Java `Future`, `CompletableFuture`, Spring `TaskExecutor`, and `@Async`, then connect them to the `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` sequence.

## 2. Timeline of an asynchronous task

General diagram of a queued executor:

```text
Thread A (caller)                           Executor / Thread B
-----------------                           -------------------
create Runnable/Callable/async invocation
       |
       +--> submit(task) ------------------> accept or reject task
       |                                        |
       |                                        +--> queue (may wait)
       |                                        |
       |                                        +--> worker starts
       |                                               |
       |                                               +--> run body
       |                                               +--> complete / throw / cancel
       |                                               +--> update Future
       |
       +--> receive Future <----------------- handle representing computation
       |
       +--> do other work
       |
       +--> future.get() / join() ----------> wait if not yet completed
                                                 |
                                                 +--> return value or report failure
```

An `ExecutorService.submit(Callable<T>)` call typically returns very quickly if accepted. The task may **have no free worker yet**, be sitting in the queue, be running, or have finished extremely fast. Therefore **you cannot infer started/completed status merely from submit returning**.

Notable exception: `Executor` is an abstraction. An executor may execute immediately on the caller thread; a `RejectedExecutionHandler.CallerRunsPolicy` can run the task directly on the calling thread when the pool is overloaded. Thus you also **cannot assert every `execute` call is asynchronous**. You must inspect the actual executor, queue, rejection policy, and invocation path.

The caller receiving a `Future` receives a **handle for observing the result**, not the computed value immediately. With `CompletableFuture`, the handle also lets you chain follow-up stages and manage errors.

## 3. Comparison table of APIs and what they guarantee

| API / operation | Immediately after return, what is known? | What is NOT automatically guaranteed? |
| --- | --- | --- |
| `Executor.execute(Runnable)` | Request was handled per executor policy if no throw | Task has started or finished; no standard result handle |
| `ExecutorService.submit(Callable<T>)` | Returns `Future<T>` if submission succeeded | `Callable` has finished; outcome succeeded |
| `ExecutorService.submit(Runnable)` | Returns `Future<?>` for tracking | Runnable threw no exception; side effects committed |
| `CompletableFuture.supplyAsync(supplier, executor)` | Returns stage representing computation on specified executor | Stage finished before return |
| `CompletableFuture.completedFuture(value)` | Future is **already** normally completed with value | Any real background task was submitted |
| `@Async` method returning `CompletableFuture<T>` | When async proxy is active, caller gets Future for invocation result | Body finished; same-class call (self-invocation) was intercepted by proxy |
| `@Async void` | Caller receives no Future from method | Can `get/join` for result/error; failure automatically throws at caller |
| `Future.isDone()` | Future is in a terminal state per API definition | It succeeded; cancellation actually stopped all side effects |
| `Future.get()` | When returning normally, holds successful result per Future | External DB/API effects are durable if body did not verify |
| `CompletableFuture.join()` | When returning normally, retrieves stage's value | Non-blocking; never throws an exception |
| `ExecutorService.shutdown()` | Executor starts rejecting new work, moving toward shutdown per contract | Queued/running tasks have already finished |

If the pool is already shut down or full under its rejection policy, `submit`/`execute` may **throw `RejectedExecutionException`** (or the corresponding Spring exception). When rejected, **no accepted task exists** to wait on; the application must handle backpressure/retry/fallback per contract.

### 3.1. Does "Accepted" equal "entered the queue"?

No. An executor may spawn a thread to run immediately, enqueue, use the caller thread, or apply another policy. "Accepted" only means the request was handled by the executor without immediate rejection. Never hardcode status `QUEUED` solely because `submit` succeeded.

### 3.2. "Completed" can be a failure

Java 17 `Future.isDone()` returns `true` when the computation ended **normally, via exception, or via cancellation**. For example:

```java
Future<String> result = executor.submit(() -> {
    throw new IllegalStateException("remote API failed");
});

// When result finishes, isDone() == true yet get() throws ExecutionException.
String value = result.get();
```

This is an **illustrative snippet assuming an `executor` in context**, not a standalone runnable file. `get()` does not return a value if the callable threw; it throws `ExecutionException` wrapping the root cause. Note that calling `get()` before the task ends **blocks**, so real-world code usually needs a timeout.

## 4. Future: when do you truly know a task has finished?

The `java.util.concurrent.Future<V>` interface provides key APIs:

- `boolean isDone()`: non-blocking; indicates the computation ended per the Future. Does not imply success.
- `boolean isCancelled()`: non-blocking; indicates the Future was canceled.
- `V get()`: blocks until completion, then returns the result or throws `ExecutionException`/`CancellationException`/`InterruptedException`.
- `V get(long timeout, TimeUnit unit)`: waits at most the chosen duration; may throw `TimeoutException`.
- `cancel(boolean mayInterruptIfRunning)`: **attempts** to cancel; does not guarantee the thread or all external actions fully stopped.

Sample usage inside caller code:

```java
Future<OrderSummary> future = executor.submit(this::buildSummary);
try {
    OrderSummary result = future.get(5, TimeUnit.SECONDS);
    publishResult(result);
} catch (TimeoutException ex) {
    future.cancel(true); // Requests cancellation, does not guarantee all side effects stopped.
    throw new IllegalStateException("Summary timed out", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException("Summary failed", ex.getCause());
}
```

This is an **illustrative snippet**, not standalone-compilable: it needs `executor`, `OrderSummary`, `buildSummary`, `publishResult`, and relevant imports. Because `get(...)` also throws `InterruptedException`, the caller must declare throws or catch and **restore the interrupt flag** appropriately; never swallow interruption.

### 4.1. A timeout does not automatically cancel the work

`get(5, SECONDS)` throwing `TimeoutException` only states **the caller waited too long**. The task may still be running. If it must stop, decide a cancellation policy and make the task cooperatively interruptible. For external I/O, **request timeouts at the HTTP/DB layer** matter more than merely bounding `get`.

### 4.2. cancel(true) does not guarantee stopping

With standard `FutureTask`/`ExecutorService`, `cancel(true)` tries to interrupt the worker if it is already running and the worker is known. The thread itself must react properly to interrupts; many I/O calls or already-started side effects cannot be "rolled back" by an interrupt.

With `CompletableFuture`, `cancel(true)` acts as exceptional completion and the `mayInterruptIfRunning` parameter **is not used to control interruption** per Java 17 Javadoc. This is a clear example that "Future was canceled" does not mean "actual work in progress immediately stopped".

### 4.3. Future results and memory consistency

Under the Java Memory Model, actions inside an asynchronous computation happen-before actions following the corresponding `Future.get()` in another thread. Thus waiting on `get` is not just polling a flag, but a result synchronization mechanism. Still, it is **not a transaction**: file writes, database commits, and message publishing still require their own confirmation/durability contracts.

## 5. CompletableFuture: a completed stage is not necessarily successful

`CompletableFuture<T>` is a `Future` that also implements `CompletionStage`:

```java
CompletableFuture<Integer> stage =
        CompletableFuture.supplyAsync(() -> 40 + 2, executor);

int value = stage.join();
```

This is an illustrative snippet in a class with `executor`. `join()` blocks as needed and returns `42` on success; if the stage completed exceptionally, `join()` throws unchecked `CompletionException`, whereas `get()` throws checked `ExecutionException`.

| State | `isDone()` | `isCompletedExceptionally()` | Result of `join()` |
| --- | --- | --- | --- |
| Not yet completed | `false` | `false` | Waits if called |
| Succeeded | `true` | `false` | Returns value |
| Failed with exception | `true` | `true` | Throws `CompletionException` usually wrapping root cause |
| Canceled | `true` | `true` | Throws `CancellationException` or matching exception |

Further distinctions:

- `thenApply(fn)` chains a stage processing the result when the prior stage succeeds.
- `thenCompose(fn)` chains the next asynchronous work returned by `fn` (flattens futures).
- `whenComplete((value,error) -> ...)` primarily observes completion; without recovery handling, a prior stage's error continues propagating.
- `exceptionally(ex -> fallback)` **can turn a failed stage into a successful stage with a fallback**. To report failures, inspect the original stage or log errors rather than only checking the post-`exceptionally` stage.
- `handle((value,error) -> ...)` can transform both success and failure paths into a new result.
- `allOf(a,b,c)` represents that **all input futures have completed**; if any input fails, `allOf` can complete exceptionally. It does not produce a list of results and does not automatically roll back/cancel other tasks.
- `anyOf(a,b,c)` completes when **one** input completes, not meaning the whole batch finished.

A proper `allOf` example:

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(customerStage, productStage, stockStage);
all.join(); // Wait for all three to complete, propagate failure if any.
```

This snippet assumes three futures were already created. If `all.join()` returns normally, all stages completed normally; if one stage failed, inspect the root cause and any side effects from the other stages.

### 5.1. supplyAsync does not automatically use Spring's TaskExecutor

`CompletableFuture.supplyAsync(supplier)` takes no executor; by default it uses `CompletableFuture`'s async execution facility (typically `ForkJoinPool.commonPool()` per the JDK). Do not mistakenly assume it always runs on the `ThreadPoolTaskExecutor` bean configured by Spring Boot.

When you need bounded threads/queues, tracing propagation, or managed shutdown, **pass a managed executor**:

```java
CompletableFuture<Report> report =
        CompletableFuture.supplyAsync(this::loadReport, managedExecutor);
```

This is an illustrative snippet. `managedExecutor` is an explicitly chosen `Executor`, and `loadReport` returns `Report`.

### 5.2. Do orTimeout and completeOnTimeout "kill" the thread?

`future.orTimeout(3, SECONDS)` completes the stage exceptionally on timeout, while `completeOnTimeout(fallback, 3, SECONDS)` can complete it normally with a fallback. Those APIs **change completion state**; they do not guarantee interrupting or canceling background work affecting external systems.

Never treat a timed-out or fallback-completed future as proof that a remote job or external transaction stopped. If the task can still produce side effects after timeout, design explicit cancellation/leases/idempotency.

## 6. Spring @Async: the proxy call returning differs from the method finishing

Spring Framework provides `@Async` to offload method execution to a `TaskExecutor`. Standard usage:

- Enable asynchronous processing with `@EnableAsync` or equivalent configuration.
- Annotate `@Async` on a method of a **Spring bean**.
- **Invoke the method through a Spring proxy**, typically from another bean; self-invocation within the same instance **bypasses** the proxy by default so the annotation may have no effect.
- When results or errors must be observed, the method should return `Future<T>` or `CompletableFuture<T>`. With `void`, the caller has no future to await; exceptions go through `AsyncUncaughtExceptionHandler`/appropriate logging.
- When a specific executor is needed, use `@Async("executorBeanName")` and register an executor bean with that name.

In default proxy mode, calling from another bean:

```java
CompletableFuture<String> handle = asyncService.loadData();
log.info("async invocation has returned"); // Does not prove task finished.
String data = handle.join();                 // Wait for result or receive failure.
```

This is an **illustrative snippet**, requiring `asyncService` to be an injected bean and `loadData` to return a future. Do not put `@Async` directly on lifecycle callbacks like `@PostConstruct` expecting the proxy to make initialization asynchronous; Spring recommends separating a bean responsible for invoking the async method on the target bean.

### 6.1. Exceptions from @Async do not automatically throw at the caller

If an `@Async CompletableFuture<T>` throws on a worker thread, the proxy call may have returned long ago. The error is reflected in the future; the caller only learns of it by calling `get/join` or attaching a completion handler to observe failures.

If the method returns `void`, the caller has no future and exceptions cannot be returned to the caller the same way; use `AsyncUncaughtExceptionHandler` or logging/monitoring. A runner invoking an `@Async void` method and returning **does not automatically fail startup** if the background work throws later.

### 6.2. Self-invocation: easy to mistake for a real submission

Counter-example:

```java
@Service
class JobService {
    void dispatch() {
        loadAsync(); // Called via this, bypasses proxy in default Spring AOP mode.
    }

    @Async
    public CompletableFuture<String> loadAsync() {
        return CompletableFuture.completedFuture("OK");
    }
}
```

This is an **illustrative class**, requiring imports for `@Service`, `@Async`, `CompletableFuture`, and `@EnableAsync`. Calling within the same bean bypasses the async proxy so the body can execute **synchronously on the caller thread**. When reviewing whether "submit has returned yet", verify whether the async proxy is actually being used.

## 7. Runnable example: Spring Boot 3.3 verifying submit != completed

This example is designed deterministically using `CountDownLatch` rather than `Thread.sleep(...)` to avoid race-dependent ordering. The background task **cannot complete** before the runner explicitly opens the latch. Thus stdout is stable, clearly showing:

- After the `@Async` call, the caller receives a future and `isDone() == false`.
- The runner opens the latch, then `future.get(...)` waits until computation succeeds.
- Only after the runner returns does Boot publish `ApplicationReadyEvent`.

### 7.1. Project structure and Gradle

Uses Java 17+, Gradle Wrapper, and Spring Boot 3.3.13.

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'submit-vs-complete-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

No web starter is needed; this tests thread timing, futures, and startup milestones without needing an HTTP port.

### 7.2. Complete Java file

Create **`src/main/java/com/example/tasks/SubmitVsCompleteApplication.java`**:

```java
package com.example.tasks;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableAsync
public class SubmitVsCompleteApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(SubmitVsCompleteApplication.class, args)) {
            System.out.println("05 main: run returned");
        }
    }

    @Bean("learningExecutor")
    ThreadPoolTaskExecutor learningExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("learning-");
        return executor;
    }

    @Bean
    ApplicationRunner verifyAsyncCompletion(AsyncWorker worker) {
        return args -> {
            CountDownLatch release = new CountDownLatch(1);

            // Invocation via Spring proxy: submit work and receive handle.
            CompletableFuture<String> handle = worker.prepare(release);

            // Worker may already be scheduled but is waiting on the latch.
            System.out.println("02 submitted: done=" + handle.isDone());

            // From here the worker is allowed to finish.
            release.countDown();

            // Must wait for the result before letting the runner finish.
            String value = handle.get(10, TimeUnit.SECONDS);
            System.out.println("03 completed: " + value);
        };
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01 ApplicationStartedEvent");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("04 ApplicationReadyEvent");
    }

    @Component
    public static class AsyncWorker {

        @Async("learningExecutor")
        public CompletableFuture<String> prepare(CountDownLatch release) {
            try {
                release.await();
                return CompletableFuture.completedFuture("data prepared");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }
        }
    }
}
```

**Why is this code verifiable?**

1. `@EnableAsync` turns on AOP async support; `AsyncWorker` is a Spring bean injected into the runner, so `worker.prepare(release)` passes through the proxy.
2. `@Async("learningExecutor")` selects the exact managed `ThreadPoolTaskExecutor` bean. Spring initializes and shuts down the bean per container lifecycle; the example does not leak custom pools.
3. `CountDownLatch(1)` starts at 1; right after the caller receives the Future, the async body **cannot finish** because it must wait on `release.await()`.
4. Because the caller has not yet called `release.countDown()`, line `02` **always** observes `handle.isDone() == false` if submission is accepted and the code runs in this configuration.
5. The runner opens the latch and calls `get(10, SECONDS)`. If the worker returns normally, `get` returns the value. If the worker throws or is interrupted, the runner receives a failure; if it times out, the runner receives `TimeoutException`. Those errors **are allowed to escape the runner**, so Boot handles startup failure instead of falsely reporting ready.
6. `ApplicationStartedEvent` arrives after refresh, before runners. `ApplicationReadyEvent` is published only after runners return normally. Thus line `04` comes **after** line `03`.
7. `try-with-resources` closes the context after `SpringApplication.run(...)` returns. Because we awaited task completion, closing the executor does not cut off the example task.

### 7.3. Run command and stdout

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

With the project exactly as above, no extra arguments, and successful task execution, **the lines explicitly printed by Java code** in order are:

```text
01 ApplicationStartedEvent
02 submitted: done=false
03 completed: data prepared
04 ApplicationReadyEvent
05 main: run returned
```

Gradle may print additional task/build lines. In the example, **the worker thread prints no logs**, so numbered lines never contend between two threads. The latch controls when the task is allowed to finish, independent of any guessed `sleep` interval.

**Key insight:** when line `02` prints, an `@Async` call has returned and the caller holds a handle, yet the task is **not yet completed**. Only after `get(...)` returns normally does `03` print. Because the runner waits, `ApplicationReadyEvent` on line `04` appears **only after the mandatory work succeeds**.

### 7.4. Trying a variant: submit and return immediately

Replace the runner body with the following (**illustrative replacement snippet**, not a standalone file):

```java
return args -> {
    CountDownLatch release = new CountDownLatch(1);
    CompletableFuture<String> handle = worker.prepare(release);
    System.out.println("submitted; done=" + handle.isDone());

    // Runner returns without releasing the latch or awaiting the handle!
    // This lets startup report ready before the task finishes.
};
```

**Do not run this variant as-is in production:** the latch is never released so the task may get stuck, prolonging shutdown. The goal is to demonstrate the contract: Boot sees the runner return and does not automatically know a Future is still waiting. If replaced with real I/O or resource waits, the same situation happens without any latch.

In real code, **store/monitor the handle** or return immediately only when the work is truly optional, and handle teardown on shutdown. If the work must finish before readiness, keep a deadline-bounded `get(timeout)`/`join` model or provide a reliable readiness gate.

### 7.5. Trying a variant: worker completes with error

Replace `prepare`'s body after `release.await()` to return:

```java
return CompletableFuture.failedFuture(
        new IllegalStateException("required initialization failed"));
```

This is a **replacement snippet inside the `@Async` method**, not standalone. `handle.get(...)` in the runner will throw `ExecutionException` wrapping the root cause; the runner fails to return normally, and Boot handles startup failure. No `ApplicationReadyEvent` occurs along the success path.

If you **omit `get(...)`** and only submit, a later worker failure may sit unobserved inside the Future; Boot may still publish ready, so you must observe failures independently and decide fallback/retry policies.

### 7.6. Trying a variant: self-invocation

Place the `@Async` method and a direct call `this.prepare(release)` inside the same `AsyncWorker` bean. In default proxy mode, the internal call **bypasses the proxy** and can run synchronously. When the body awaits `release.await()` while release is only triggered after the method returns, you create a deadlock. That is why the experiment uses **two beans** and injects the container proxy.


## 8. Spring Boot startup: does a runner submitting background work make the app ready?

In the Boot 3.3.x flow:

```text
ApplicationContext refreshed
   |
   +--> ApplicationStartedEvent
   +--> LivenessState.CORRECT
   |
   +--> invoke ApplicationRunner / CommandLineRunner
   |      +--> executor.submit(job)
   |      |      +--> queued/running/pending
   |      +--> runner returns
   |
   +--> ApplicationReadyEvent
   +--> ReadinessState.ACCEPTING_TRAFFIC
```

**Spring Boot awaits the runner call, not every async job the runner submitted.** If `run(...)` exits right after `submit`, Boot can still reach ready while the job remains pending.

This becomes a real problem when the job is a hard prerequisite: loading a catalog, warming essential caches, syncing access permissions, or running data safety checks before accepting traffic. False readiness can lead a load balancer to route traffic to an instance without required data.

Categorizing work:

| Work category | Need to wait before ready? | Approach |
| --- | --- | --- |
| Mandatory initialization for every request | **Yes**, by contract | Runner awaits Future success with timeout, or explicit readiness gate |
| Optional cache refresh with valid fallback | Possibly not | Submit, track degraded status, bounded retries |
| Non-blocking background maintenance | Not necessarily | Manage via executor/scheduler lifecycle and monitoring |
| Task serving one HTTP request | Caller/request-specific | Return 202 + job ID or await per SLA; do not use startup readiness for per-request results |
| Long-lived stream/consumer | Cannot "complete" like batch | SmartLifecycle start/stop, separate "subscribed and ready" check |

### 8.1. ApplicationStartedEvent and ApplicationReadyEvent do not observe all tasks automatically

`ApplicationStartedEvent` fires once the context is refreshed, before runners. `ApplicationReadyEvent` fires after runners finish their **synchronous calls**. Boot's liveness/readiness have application-level meaning but do not infer that every custom thread has finished.

A `SmartLifecycle.start()` that merely submits a task and returns can be misunderstood the same way: the component was asked to start, yet the worker is not truly ready.

### 8.2. When work does not block ready, do not hide errors

For optional background tasks, letting Boot become ready is fine as long as **the fallback is genuinely valid**. You need:

- Dedicated metrics: `submitted`, `running`, `succeeded`, `failed`, `cancelled`, `rejected`.
- Bounded retries + backoff/jitter for recoverable failures, never infinite retries.
- Degraded/health states reflecting required capabilities.
- Shutdown task termination paths and crash recovery capability.
- Tracing/correlation IDs propagated from request to background work.

Never use "submitted" to record a business record as **DONE**. If an API returns immediately, its status should be `ACCEPTED`/`PENDING`, updating to `SUCCEEDED`/`FAILED` only after completion with proper proof.

## 9. HTTP 202 Accepted is not the final successful result

When a client submits a long job and the server returns `HTTP 202 Accepted`, standard semantics say the request was accepted for processing, yet processing may **not be complete** and may fail later. This closely mirrors `ExecutorService.submit`.

An appropriate API design:

```text
POST /reports
-> 202 Accepted
-> {"jobId":"rpt-123","status":"PENDING","statusUrl":"/reports/rpt-123"}

GET /reports/rpt-123
-> {"jobId":"rpt-123","status":"RUNNING"}

GET /reports/rpt-123
-> {"jobId":"rpt-123","status":"SUCCEEDED","downloadUrl":"/reports/rpt-123/file"}
```

This is an **illustrative HTTP transcript**, not a Spring Controller implemented in the runnable example. If the task fails, the final status must clearly report `FAILED` and a non-sensitive reason.

**Specifically:** HTTP 202 only states the request was accepted under the HTTP contract. It **does not automatically create a durable queue**, guarantee job survival across JVM restarts, or provide idempotency or status tracking. If the server uses only an in-memory executor, a process crash can lose "accepted" but unprocessed work. For critical jobs, consider a database-backed job table, durable message broker, outbox pattern, and recovery worker.

### 9.1. Relationship with transactions

If a method inside a transaction submits a background task, the async thread **does not automatically inherit the caller's transaction context**. The task may execute before the caller commits and miss uncommitted data; or the caller's transaction may roll back after the task already sent an external message.

For tasks that must run only after commit, use transaction synchronization/`@TransactionalEventListener(phase = AFTER_COMMIT)`, an outbox, or an appropriate queue. Do not treat "calling submit after a save call" as proof the transaction committed.

## 10. Task queues, thread pools, and backpressure

A `ThreadPoolTaskExecutor` can have:

- `corePoolSize` and `maxPoolSize`: workers maintained/scaled per configuration.
- `queueCapacity`: queue capacity when threads are busy.
- `RejectedExecutionHandler`: determines what happens when the executor cannot accept work.
- Thread names, metrics, and timeout/shutdown policies configured appropriately.

Three distinct operational states:

```text
ACCEPTED but QUEUED   -> not yet executed by a thread
RUNNING               -> worker is executing
COMPLETED             -> worker has finished (success/failure/cancel)
```

A deep queue can make "submit latency" low while "time-to-start" and "time-to-complete" are high. If you only measure quick `submit` returns, dashboards can look green while users wait minutes.

For servers receiving many jobs, design **backpressure**:

- Bound concurrency and queues to real resources; avoid unbounded queues that grow memory.
- Under overload, reject intentionally (e.g., HTTP 429/503 per API contract) or route to a durable job system with explicit capacity.
- Measure `queue wait` separately from `execution duration` and `end-to-end completion latency`.
- Do not infinitely retry immediately on `RejectedExecutionException`.
- Do not let `CallerRunsPolicy` accidentally block event-loop/HTTP request threads for too long when the pool is busy.
- When queues fill, monitor rejected counts, active tasks, queue depth, timeouts, and failure rates.

**Note:** `ThreadPoolTaskExecutor` is a lifecycle-managed Spring bean. Creating an unclosed `new ThreadPoolExecutor(...)` manually can retain threads, cause leaks, and prevent clean shutdown. Define clear executor ownership and shutdown methods.

## 11. Shutdown: "called shutdown" still does not mean all tasks finished

`ExecutorService.shutdown()` starts shutdown and stops accepting new tasks; it **does not wait until all running tasks finish**. You can use `awaitTermination(timeout, unit)` to wait for the executor to terminate, checking the boolean return value and handling timeouts.

Illustration:

```java
executor.shutdown();
boolean finished = executor.awaitTermination(10, TimeUnit.SECONDS);
if (!finished) {
    // The system needs an explicit policy for pending/in-flight tasks.
}
```

This is an illustrative snippet where `executor` exists, not standalone. `shutdownNow()` also only **attempts** to stop running tasks and returns unstarted tasks in some executors; it does not guarantee all side effects ceased.

In Spring Boot, a `TaskExecutor` bean's lifecycle integrates with context shutdown, yet task waiting behavior and timeouts depend on executor type and configuration. When jobs must not be lost, do not rely solely on JVM shutdown hooks. Use durable queues/checkpoints/idempotent jobs when work must survive crashes.

### 11.1. Difference between Future completed and business committed

A succeeded `Future` only means the method/task returned normally. If the task:

1. Sent an HTTP request without checking the response,
2. Wrote to a database before the transaction committed,
3. Put a message into a buffer without broker acknowledgment,
4. Spawned a second background thread and returned,

then the first `Future` completing **is not enough** to confirm the final business outcome. The task API must define "success" at the appropriate checkpoint; if broker ack is required, await acknowledgment before returning success.

## 12. Writing tests without relying on sleep duration

Using `Thread.sleep(100)` followed by `assertFalse(future.isDone())` can pass or fail based on machine speed, CPU contention, and CI load. Use synchronization primitives instead:

- `CountDownLatch`: creates a barrier controlling when a task may proceed/complete.
- `CyclicBarrier` or `Phaser`: coordinates multiple threads across defined phases.
- `Future.get(timeout)`: bounds waiting and catches structured failures.
- `CompletableFuture`: creates manually completable stages in unit tests to verify dependent callbacks.
- `Awaitility` or bounded polling when observing async events and eventual consistency.

For integration tests, verify **both paths**:

1. After submitting work but before releasing the latch: `future.isDone() == false`, business status is `PENDING/RUNNING` rather than `DONE`.
2. After releasing the latch, the Future completes normally and the caller observes the result: status moves to `SUCCEEDED`.
3. Task throws exception: Future completes exceptionally, status must be `FAILED`, not `SUCCEEDED`.
4. Executor rejects: no handle may be returned; request must reflect rejection.
5. Task is canceled/timed out: must report proper status and clarify whether side effects might continue.
6. Runner awaits mandatory task: ready arrives only once task succeeded.
7. Runner only submits optional task: readiness aligns with fallback and monitoring contracts.

Never write assertions depending on log ordering from two threads without synchronization; use latches/futures to verify happens-before relationships.

## 13. Common mistakes

| Claim or symptom | Why it is wrong | How to fix |
| --- | --- | --- |
| "`submit` returned so the job is finished" | May still be queued or running | Track Future/ACK and explicit status |
| "`isDone() == true` means success" | Failure/cancellation also produce done | `get/join`, `isCompletedExceptionally`, and result contract |
| "Having a future means work definitely started" | May still be waiting in queue for a thread | Distinguish accepted/queued/running |
| "`cancel(true)` surely cuts off all I/O" | Interrupt/cancellation is best effort; CompletableFuture does not interrupt | I/O timeouts, cooperative cancellation, idempotency |
| "`get(timeout)` automatically cancels the task" | Only times out the waiting caller | Explicit cancel, downstream deadlines |
| "`@Async` in the same class always runs on another thread" | Self-invocation bypasses proxy | Call via another bean/valid proxy |
| "`@Async void` exception makes caller throw" | Caller has no Future | Handler/logging/metrics, return Future when result needed |
| "`CompletableFuture.supplyAsync` always uses Spring executor" | Without an executor it typically uses common pool | Pass an executor bean with clear capacity |
| "Runner submits and returns so Boot awaits all background jobs" | Boot only awaits the runner call | Await mandatory Futures or readiness gate |
| "HTTP 202 means processing finished" | 202 means accepted, possibly still pending | Job ID, status endpoint, durability |
| "Future succeeded so DB surely committed" | Task might not have awaited commit/ack | Define success at business boundary |
| "Last task finished so all tasks finished" | Earlier/other tasks may differ | Use `allOf` or proper batch tracking |
| "`shutdown` returned so executor has no tasks left" | Shutdown only initiates stopping | `awaitTermination` and timeouts |
| "Longer queue is safer, no lost jobs" | In-memory queues can be lost on process crash | Bounded queues/appropriate durable brokers |
| "Using `Thread.sleep` makes async tests stable" | Race depends on scheduling | Latches, barriers, timeout-bounded futures |

### 13.1. Checklist for debugging a "submitted but no result yet" job

1. Find the **exact submission site**: `execute`, `submit`, `@Async`, `supplyAsync`, or external queue?
2. Check whether submission threw/rejected; if so, the request was never accepted.
3. Identify the real executor and thread name; are Spring proxy and `@EnableAsync` active?
4. Read metrics for queue size, active threads, completed/failed counts, and task wait time.
5. Inspect the Future: `isDone`, `isCancelled`, `isCompletedExceptionally`, `get`, or completion callbacks.
6. Check worker exceptions; especially `@Async void` and unobserved Futures.
7. Verify business ACK: DB commit, file fsync when needed, broker ack, valid downstream response.
8. Check whether the caller has timeouts and cancellation policies; is a thread stuck on I/O?
9. If occurring at startup, check whether runners returned and `ApplicationReadyEvent` fired.
10. If transactions are involved, check whether the async thread ran before commit.
11. If the JVM restarts, can the system recover pending jobs? Is an in-memory queue appropriate?
12. Log task ID, phase, duration, outcome, and correlation ID; never log secrets/sensitive payloads.

## 14. Exercises and self-check questions

**Q1.** An `ExecutorService.submit` returns a Future immediately. Is the work complete?

**A:** Not enough evidence. The Future may still be queued/running. Check completion and inspect the outcome.

**Q2.** `future.isDone()` is true and `get()` throws `ExecutionException`. Did the task succeed?

**A:** No. It ended **in failure**.

**Q3.** An `@Async` method is called directly within the same bean. Is it guaranteed to run on a worker thread?

**A:** No, in default proxy mode self-invocation is not intercepted.

**Q4.** A runner submits a mandatory job and returns; Boot publishes the Ready event. Does that prove the job completed?

**A:** No. Boot only knows the runner returned. You must await Future success or control readiness explicitly.

**Q5.** Does calling `CompletableFuture.cancel(true)` guarantee interrupting background work?

**A:** No. For CompletableFuture, cancel performs exceptional completion; the `mayInterruptIfRunning` flag does not control interruption per the API.

**Q6.** `future.get(5, SECONDS)` throws TimeoutException. Has the task been canceled?

**A:** No. Only the caller's wait time expired. The task may keep running.

**Q7.** `@Async void` throws an exception. Does the caller automatically receive `ExecutionException`?

**A:** No, because the caller has no Future. You need another handler/monitoring or change the API to return a Future.

**Q8.** An API `POST /reports` returns 202. Is the report data ready to download?

**A:** Not necessarily. You need a status endpoint and an actual `SUCCEEDED` status/download link.

**Q9.** Does `ExecutorService.shutdown()` returning prove all tasks finished?

**A:** No. That only signals shutdown started; use `awaitTermination`/track Futures.

**Q10.** When can a completed Future still lack business success?

**A:** When the task returns before database commit, broker acknowledgment, remote operation, or a secondary background task.

## 15. Takeaways and official references

- **Submitted/accepted** means work was handed off per the executor contract, not necessarily started or completed.
- **Completed** encompasses success, failure, and cancellation; `isDone` alone does **not** confirm success.
- **Future.get / CompletableFuture.join** allow waiting/observing results, while requiring timeouts, exception handling, interruption handling, and verified business ACKs.
- **Spring @Async** requires `@EnableAsync` and proxy invocation; return a Future when the caller needs outcomes, avoiding `void` for mandatory work.
- **A Spring Boot runner** that merely submits and returns can let `ApplicationReadyEvent` fire **before the task actually finishes**.
- **Queues/executors** need capacity bounds, rejection handling, monitoring, and shutdown lifecycles; acceptance into an in-memory queue does not mean durable.
- **HTTP 202 Accepted** and job status `PENDING` do not mean `SUCCEEDED`; provide a job ID and tracking endpoint.
- **For mandatory startup tasks**, await verified results with a timeout or explicit readiness gate; never use sleep to guess timing.

References:

- [Java SE 17 — Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html), `isDone`, `get`, `cancel`, and memory consistency.
- [Java SE 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html), exceptional completion, `join`, `allOf`, cancellation.
- [Spring Framework 6.1 — @Async API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html), supported return types and proxies.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html), `@EnableAsync`, `@Async`, async exception handling.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), lifecycle events, runners, and readiness.
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html), pool/queue semantics and lifecycle.

To answer "is the job done?", clearly distinguish **submitted**, **started by a worker**, **how the Future completed**, **whether the caller inspected the outcome**, and **whether business side effects were confirmed**. These are independent boundaries that must be measured, not substituted for one another with a single "submitted" log.
