# Steps Without the Async Suffix May Run on the Completion Thread

In Java 17+ and Spring Framework, `CompletableFuture` lets you compose processing steps with `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `handle`, `thenCombine`, and more. A very common misconception is: "Since I used `CompletableFuture`, every callback runs on a background thread," or "a callback chained after an `@Async` method will always use the exact executor declared on `@Async`."

**Incorrect.** Under `CompletableFuture`'s execution policy, actions of methods **without the `Async` suffix** may be executed by **the thread that causes the preceding future to complete**, or another thread participating in the completion operation. If the stage is already complete when you register the callback, the callback may run **immediately on the registering thread**. Therefore, a callback without the `Async` suffix **has no thread-switching guarantee**.

This is foundational knowledge in the **CompletableFuture Composition** group of the **Spring Framework – concurrency** module: you need to know where a callback can run before placing thread-blocking queries, heavy computation, transaction logic, logging context, or thread-dependent code inside it.

## 1. Visualizing a CompletableFuture Chain

```text
Thread "request"
     |
     | register callback
     v
CompletableFuture<String> source
     |
     +-- thenApply(transform) ------------> stage B
     |             ^
     |             | may run on thread completing source
     |
     +-- thenApplyAsync(transform, pool) --> stage C
                   |
                   | schedules callback via specified executor
                   v
              pool worker
```

Two points to distinguish:

1. **A stage may still be incomplete** even though a callback-registration method like `thenApply(...)` has returned a new `CompletableFuture`.
2. **The thread running the callback** is not necessarily the thread that called the registration method; for non-`Async` methods, that thread depends on completion timing and mechanics.

"Without `Async`" **does not mean** "always runs on the main thread," "always runs synchronously end-to-end," or "always runs on the thread where the producer was started." It means **no separate executor is requested to hand off the callback** under the non-async policy.

### Key Terms to Understand

| Term | Role |
| --- | --- |
| `CompletableFuture<T>` | Represents a result that can complete in the future; may complete normally, exceptionally, or be cancelled |
| `CompletionStage<T>` | API for composing steps dependent on a future result |
| Upstream stage | The input stage that a callback waits on |
| Dependent stage | The new stage returned by `thenApply`/`thenCompose`/... |
| Completion thread | The thread performing the upstream completion action, e.g., calling `complete(...)` or finishing an async computation |
| Registration thread | The thread calling `thenApply(...)` to attach a callback |
| Executor | Object accepting tasks to schedule execution, e.g., `ThreadPoolTaskExecutor` or `ExecutorService` |

A new stage can itself be the upstream for subsequent stages; each link has its own execution rules.

## 2. Official Policy: Non-Async Has No Thread Affinity

The Java SE 17 `CompletableFuture` Javadoc states the policy for **non-async** dependent completion actions: they *may be performed by the thread that completes the current CompletableFuture, or by any other caller of a completion method*. This is a **may** policy, not a promise pinning which thread will run.

Keep three scenarios in mind:

### Scenario A — Callback Registered While Upstream Is Incomplete

```java
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<String> next =
        source.thenApply(String::toUpperCase);

source.complete("hello");
```

In typical JDK 17 implementations, if the callback is registered before `complete` and there is no competing completion operation, the thread calling `source.complete("hello")` may execute `String::toUpperCase` directly while processing dependent completions.

**Do not treat thread names as a contract here.** If multiple threads participate in completion or there is a race between registration and completion, the actual thread can differ. What is semantically guaranteed is that **the dependent stage computes the right result**, not thread identity.

### Scenario B — Upstream Already Completed Before Callback Registration

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("hello");

CompletableFuture<String> next =
        ready.thenApply(String::toUpperCase);
```

In standard JDK 17 implementations, the `thenApply` callback may run **immediately upon calling `thenApply` on the registration thread**, because the input value is already available.

**Consequence:** if the work inside `thenApply` takes 500 ms, registering the callback on a request thread can take nearly 500 ms. Do not assume "because it is a Future callback, registration is always near-instant."

### Scenario C — Future Completes on an Executor Worker

```java
ExecutorService worker = Executors.newSingleThreadExecutor();

CompletableFuture<String> source =
        CompletableFuture.supplyAsync(() -> "hello", worker);

CompletableFuture<String> next =
        source.thenApply(String::toUpperCase);
```

This is a **fragment**, requiring imports and shutting down `worker`. When the `supplyAsync` task finishes after the callback is registered, the non-async callback **may run on the worker that just completed upstream**. If upstream completes fast enough before `thenApply` is called, the callback may run inline on the registration thread. Reading just two lines of code is not enough to determine the thread name.

**Summary:** a non-async method **may run on the completion thread**, yet **is not promised to always run on that thread**.

## 3. Comparing Methods With and Without the Async Suffix

| Non-Async | Corresponding Async | Scheduling difference |
| --- | --- | --- |
| `thenApply(fn)` | `thenApplyAsync(fn)` | Async requests executing `fn` via the default asynchronous execution facility |
| `thenApply(fn)` | `thenApplyAsync(fn, executor)` | Allows choosing an explicit executor for `fn` |
| `thenAccept(action)` | `thenAcceptAsync(action, executor)` | Action receives the result, returns `CompletableFuture<Void>` |
| `thenRun(action)` | `thenRunAsync(action, executor)` | Action does not receive the input result |
| `thenCompose(fn)` | `thenComposeAsync(fn, executor)` | Async dispatches the function creating the child stage via the executor |
| `thenCombine(other, fn)` | `thenCombineAsync(other, fn, executor)` | Combiner function is scheduled via the executor |
| `whenComplete(action)` | `whenCompleteAsync(action, executor)` | Result/error observation callback can also be scheduled |
| `handle(fn)` | `handleAsync(fn, executor)` | Success/error transformation function runs via the executor |

Some operations like `exceptionally(...)` have async versions in modern Java releases (`exceptionallyAsync(...)` in Java 12+); check the API of your JDK version. Methods **without the Async suffix** in the table carry no thread-identity guarantee.

### 3.1. What Does Default Async Use?

For `CompletableFuture`, the `thenApplyAsync(fn)` overload without an `Executor` uses the **default asynchronous execution facility**, typically `ForkJoinPool.commonPool()` in Java 17. The Javadoc also notes that if the common pool does not support a parallelism level of at least 2, the implementation may use a new thread per task. This is **`CompletableFuture`'s policy**, and does not automatically pick Spring's `ThreadPoolTaskExecutor`.

Therefore:

```java
var step = source.thenApplyAsync(this::heavyCalculation);
```

This does not mean `step` uses Spring's `applicationTaskExecutor` or `reportExecutor` bean. If you want to ensure the execution handoff goes to a chosen pool, pass an explicit executor:

```java
var step = source.thenApplyAsync(this::heavyCalculation, cpuExecutor);
```

Both snippets above are **fragments**: `source`, `heavyCalculation`, and `cpuExecutor` must exist in the application class.

### 3.2. Async Does Not Necessarily "Create a New Thread"

The `Async` suffix means the callback is **scheduled according to the executor's policy**, not "starts `new Thread` for every callback" or "guaranteed to be a different thread."

A custom `Executor` like:

```java
Executor direct = Runnable::run;
future.thenApplyAsync(value -> transform(value), direct);
```

can execute the action **directly on the thread calling `execute`**, because a direct executor runs `Runnable.run()` in place. A saturated pool's `CallerRunsPolicy` can also force the caller to run the work directly. Thus, if a system needs **resource isolation or to avoid blocking request threads**, you must control the executor's behavior, overload/rejection policy, and task duration—not just add the `Async` suffix.

## 4. Runnable Java 17 Example: Three Distinct Thread Cases, Deterministic Output

The following program illustrates three cases:

1. `thenApply` registered **before** `source` completes; the producer worker calls `complete`.
2. `thenApply` attached to `completedFuture` directly on the registration thread.
3. `thenApplyAsync` using an **explicitly specified executor** to run the callback.

Use `CountDownLatch` instead of `Thread.sleep(...)` to enforce deterministic event ordering. Explicitly name threads so stdout does not depend on OS/JVM-assigned names.

Save as **ContinuationThreadDemo.java**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ContinuationThreadDemo {
    private static ExecutorService oneWorker(String name) {
        return Executors.newSingleThreadExecutor(
                task -> new Thread(task, name));
    }

    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("registration-thread");

        ExecutorService producer = oneWorker("completion-worker");
        ExecutorService cpu = oneWorker("cpu-worker");
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> source = new CompletableFuture<>();

            Future<?> producerJob = producer.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    source.complete("payload");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    source.completeExceptionally(e);
                }
            });

            started.await();

            // Source not yet complete: callback already registered.
            CompletableFuture<String> deferred =
                    source.thenApply(value ->
                            Thread.currentThread().getName() + ":" + value);

            release.countDown();
            String a = deferred.join();
            producerJob.get();

            // Source already completed before callback registration.
            CompletableFuture<String> ready =
                    CompletableFuture.completedFuture("ready");
            String b = ready.thenApply(value ->
                    Thread.currentThread().getName() + ":" + value).join();

            // Explicitly specify where to execute async action.
            String c = ready.thenApplyAsync(value ->
                    Thread.currentThread().getName() + ":" + value,
                    cpu).join();

            System.out.println("pending thenApply -> " + a);
            System.out.println("completed thenApply -> " + b);
            System.out.println("explicit thenApplyAsync -> " + c);
        } finally {
            release.countDown();
            producer.shutdownNow();
            cpu.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac ContinuationThreadDemo.java
java ContinuationThreadDemo
```

**Stdout of the program above when run on Java 17 under the described setup:**

```text
pending thenApply -> completion-worker:payload
completed thenApply -> registration-thread:ready
explicit thenApplyAsync -> cpu-worker:ready
```

**Why is this not just luck?**

- `started.await()` guarantees the producer task has started and is waiting on `release`, giving the registration thread time to attach `thenApply` before the producer calls `complete`.
- Only the producer thread calls `source.complete(...)` after the latch opens, with no other thread racing to complete `source`. Under JDK 17's non-async mechanism, the dependent action executes on `completion-worker` in this scenario.
- `ready` is created via `completedFuture` right on `registration-thread`; the short `thenApply` callback already has its input at registration time.
- `thenApplyAsync(..., cpu)` submits the callback to the `cpu` executor, which has a single thread named `cpu-worker`.
- Results are stored in three variables and **printed from `main` in fixed order**, rather than printing directly from three callbacks that could interleave on stdout.
- `finally` shuts down both executors. `shutdownNow` here is only to clean up demo resources; applications need an appropriate graceful shutdown policy.

**Scope of conclusion:** the demo determines execution threads **given the latches, thread factories, and JDK 17 implementation in use**; do not turn these outputs into a rule that all non-async `CompletableFuture` callbacks in every system always run on the same thread names.

## 5. Non-Async Forwarding: It Can "Eat" the Completion Thread's Time

Suppose an I/O task finishes on worker `io-1`, and then registers:

```java
CompletableFuture<Invoice> parsed =
        fetchInvoiceAsync(id)
                .thenApply(this::parseInvoice)
                .thenApply(this::validate)
                .thenApply(this::calculateLargeReport);
```

This is a **fragment**, without implementations for `Invoice`/methods. The problem is not calling `thenApply` multiple times, but **what the callbacks do** and **which thread executes them**.

If `fetchInvoiceAsync` has not completed when the dependent actions are registered, the exact same thread that just finished I/O may continue executing those callbacks. When `calculateLargeReport` burns CPU for hundreds of milliseconds, the completion thread ends up doing extra CPU work instead of becoming free for other tasks.

Consequences can include:

- A `ThreadPoolTaskExecutor` worker is occupied longer than expected; queued tasks wait longer.
- If upstream completes on an HTTP/Netty event-loop thread, a blocking callback can stall the entire event loop.
- If upstream already completed before registration and the non-async callback runs inline on the caller, the request thread can block right on the `thenApply` statement.
- When multiple dependent stages exist, do not predict their execution order from code order; avoid side effects requiring ordering beyond explicit dependencies.
- If a callback throws an exception, the dependent future can complete exceptionally; that error does not necessarily surface synchronously where the caller invoked `thenApply` in all situations.

### 5.1. Offloading CPU Work to an Appropriate Executor

```java
CompletableFuture<Invoice> result =
        fetchInvoiceAsync(id)
                .thenApply(this::parseSmallPayload)
                .thenApplyAsync(this::calculateLargeReport, cpuExecutor);
```

**Meaning:** `parseSmallPayload` is a small step that can stay inline if assessed safe; `calculateLargeReport` is delegated to a dedicated `cpuExecutor`. In practice, if parsing is also CPU-heavy or can block, move that step to an appropriate executor as well.

Do not default to `ForkJoinPool.commonPool()` for every kind of work in a web service when you need quotas, logging, saturation controls, and Spring bean lifecycle management.

### 5.2. Async on One Step Does Not "Spread" to All Subsequent Steps

```java
var b = source.thenApplyAsync(this::cpuStep, cpuExecutor);
var c = b.thenApply(this::nextStep);
```

`cpuStep` is scheduled on `cpuExecutor`, but `nextStep` **is non-async**. If `b` has not completed when `nextStep` is registered, `nextStep` may run directly on the thread completing `b`—often the worker executing `cpuStep`. If `b` is already complete when `nextStep` is registered, the action may run inline on the thread executing the second line.

There is no "executor permanently attached to the chain" just because an earlier step used `thenApplyAsync(..., cpuExecutor)`. **Each link must explicitly decide** whether dispatch is needed.

## 6. Non-Async Methods to Watch Beyond thenApply

### 6.1. `thenAccept` and `thenRun`

```java
stage.thenAccept(result -> saveToDatabase(result));
stage.thenRun(() -> refreshCache());
```

`thenAccept` receives the upstream result; `thenRun` receives no result. Both are non-async in those two lines. If the DB/cache actions perform blocking I/O, they can **block the completion thread or the caller**.

If the workload is heavy or must be isolated, use `thenAcceptAsync(..., ioExecutor)` or `thenRunAsync(..., executor)` with an appropriate executor. Also, do not treat these actions as part of an upstream transaction when threads and boundaries differ.

### 6.2. `whenComplete` Is Not Just a "Lightweight Observer" by Default

```java
CompletableFuture<Order> observed = stage.whenComplete(
        (value, error) -> audit(value, error));
```

This is a fragment. `whenComplete` creates a dependent stage and runs the action when upstream completes. If `audit` logs a short line, cost may be tiny; if `audit` makes a REST call or runs multiple queries, the callback can tie up the completion thread.

**Error semantics:** `whenComplete` is primarily for observing results/errors, not turning a failure into success like `handle`. If the action throws an error, the dependent stage may receive a failure per `whenComplete`'s rules; do not use `whenComplete` expecting to "swallow all exceptions" by default.

### 6.3. `handle` and `exceptionally` Are Also Non-Async

```java
CompletableFuture<String> recovered =
        stage.handle((value, error) ->
                error == null ? value : "fallback");
```

`handle` runs when the stage completes normally or exceptionally and **transforms** the result. `exceptionally` handles only the exceptional path. Both can run on the completion thread when calling their non-async versions.

A fallback that calls an external service can block a worker, so do not assume error-handling code is lightweight. Where supported by the JDK, `handleAsync(..., executor)` or `exceptionallyAsync(..., executor)` routes expensive fallback steps properly.

### 6.4. `thenCompose` vs. `thenApply`

Suppose `fetchProfileAsync` returns a `CompletionStage<Profile>`. When composing:

```java
CompletableFuture<Receipt> chain =
        lookupUserAsync(id)
                .thenCompose(user -> fetchReceiptAsync(user));
```

Non-async `thenCompose` **may run the `user -> fetchReceiptAsync(user)` function on the upstream completion thread**. However, that **does not mean the entire receipt fetch runs on the same thread**: the stage returned by `fetchReceiptAsync` can perform I/O or complete elsewhere. `thenCompose` simply flattens `CompletionStage<CompletionStage<T>>` into a single result stage.

If **initiating** the child request also needs a thread switch, use `thenComposeAsync(user -> fetchReceiptAsync(user), executor)`. Avoid calling `join()` inside `thenCompose`; chaining by returning the child stage itself is far better:

```java
// Avoid if potentially blocking:
.thenApply(user -> fetchReceiptAsync(user).join())

// Prefer composition, do not block callback waiting on child stage:
.thenCompose(user -> fetchReceiptAsync(user))
```

The two lines above are **chain fragments**, not a standalone program.

### 6.5. `thenCombine`, `runAfterBoth`, `allOf`

- `thenCombine(a, b, fn)` runs `fn` once both input stages have successful results; in the non-async variant, the callback may execute on the thread completing either stage or a thread participating in completion.
- `runAfterBoth` takes a callback that receives no results; it has an Async counterpart if execution needs to move.
- `CompletableFuture.allOf(a, b)` returns a future dependent on the input futures. If you chain `allOf(...).thenRun(this::aggregate)`, the `aggregate` step is still **non-async** and has no dedicated thread of its own.
- `anyOf` likewise creates a completion stage triggered by any completion; chained callbacks afterward must be analyzed the same way.

**Rule:** having **multiple upstream futures** gives no guarantee about which thread runs the final callback. Dependencies govern **when processing is allowed**, not **which thread executes it**.

## 7. Spring Context: @Async Executor Does Not Auto-Propagate to Continuations

In Spring Framework, `@EnableAsync` and `@Async("ioExecutor")` can dispatch a method onto a `ThreadPoolTaskExecutor` bean named `ioExecutor`. Yet caller code may chain onto the `CompletableFuture`:

```java
CompletableFuture<String> loaded = dataService.loadAsync(id);

CompletableFuture<Result> result =
        loaded.thenApply(this::heavyTransform);
```

The question **"Does `heavyTransform` run on `ioExecutor` or on the HTTP request thread?"** cannot be answered with a single fixed thread name:

- If `loaded` is not yet done when `thenApply` registers, the non-async callback may run on the thread completing the future (typically associated with an `ioExecutor` worker).
- If `loaded` completes before `thenApply` registers, the callback may run inline on the request thread.
- If other code participates in completing the dependent stage, another execution path may occur per completion policy.
- `@Async` configures the interceptor for the **annotated method**; it **does not attach a default executor to all dependent callbacks** after the method returns a Future.

**Do not assume `thenApplyAsync` without an executor will pick `ioExecutor`.** It uses `CompletableFuture`'s default asynchronous execution facility, normally the JDK's common pool, rather than inheriting the Spring bean.

### 7.1. Complete Spring Boot 3.x Example

The following example uses **Java 17+**, **Spring Boot 3.x/Spring Framework 6.x** with the `spring-boot-starter-web` dependency. Two executors are declared explicitly:

- `ioExecutor` handles `@Async` work simulating blocking data reads.
- `cpuExecutor` handles CPU-bound continuations via `thenApplyAsync(..., cpuExecutor)`.

Save as **src/main/java/com/example/demo/ContinuationApplication.java**:

```java
package com.example.demo;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class ContinuationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContinuationApplication.class, args);
    }

    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(50);
        pool.setThreadNamePrefix("io-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }

    @Bean("cpuExecutor")
    ThreadPoolTaskExecutor cpuExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(30);
        pool.setThreadNamePrefix("cpu-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }
}

@Service
class DataService {
    @Async("ioExecutor")
    public CompletableFuture<String> loadAsync(String id) {
        try {
            Thread.sleep(150); // Simulate blocking I/O read
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return CompletableFuture.completedFuture("item:" + id);
    }
}

@Service
class WorkflowService {
    private final DataService dataService;
    private final Executor cpuExecutor;

    WorkflowService(
            DataService dataService,
            @Qualifier("cpuExecutor") Executor cpuExecutor) {
        this.dataService = dataService;
        this.cpuExecutor = cpuExecutor;
    }

    public CompletableFuture<String> process(String id) {
        return dataService.loadAsync(id)
                .thenApplyAsync(
                        value -> value.toUpperCase(Locale.ROOT),
                        cpuExecutor);
    }
}

@RestController
class WorkflowController {
    private final WorkflowService workflow;

    WorkflowController(WorkflowService workflow) {
        this.workflow = workflow;
    }

    @GetMapping("/process/{id}")
    public CompletableFuture<String> process(@PathVariable String id) {
        return workflow.process(id);
    }
}
```

Run using a Spring Boot build with matching dependencies:

```bash
./gradlew bootRun
curl -s http://localhost:8080/process/Z1
```

On Windows, use `gradlew.bat bootRun`. When the request is accepted and both steps succeed, the response body is:

```text
ITEM:Z1
```

**Flow explanation:**

1. Spring instantiates the `ThreadPoolTaskExecutor` beans and manages their initialization/shutdown.
2. The controller calls `WorkflowService.process`; that service calls a separate bean `DataService`, so `loadAsync` goes through the Spring `@Async` proxy in default mode.
3. `loadAsync` runs on an `ioExecutor` worker. `Thread.sleep` only simulates blocking I/O; **it is not non-blocking I/O**.
4. `thenApplyAsync(..., cpuExecutor)` routes the transformation step to `cpuExecutor`, without depending on which thread completed `loadAsync`. `toUpperCase` here is lightweight for illustration; in reality split pools when tasks are substantial enough or isolation is required.
5. The controller returns `CompletableFuture<String>` so Spring MVC handles the result once complete. **The HTTP client still waits for the response body**; this is not an API returning an immediate 202 job ID.
6. If a pool saturates or a step throws an exception, the request will not return a success response like the example; map errors/overloads according to the application contract.

**Key takeaway:** using `@Async("ioExecutor")` on the source method does not force downstream `thenApply(...)` callbacks to use `ioExecutor`. To keep heavy computation off I/O workers or request threads, decide at **the callback itself** using `thenApplyAsync(..., cpuExecutor)`.

### 7.2. Why Not Create a New Executor Per Request?

Calling `Executors.newFixedThreadPool(...)` inside a controller or service per request causes thread explosion, poor observability, and unmanaged shutdown outside Spring. Create **shared executor beans** with clear limits and inject them via qualifiers.

If a custom `TaskExecutor` becomes overloaded, it may reject scheduling. Separating pools **isolates resources**, yet does not guarantee tasks are always accepted; still monitor queues, active threads, and handle rejection errors.

## 8. ThreadLocal, MDC, Spring Transactions, and Security Context

A non-async callback can run on different threads depending on timing. This makes logic relying on **thread-local state** hazardous.

### 8.1. MDC Logging

If a callback calls `MDC.get("traceId")` assuming the HTTP request's ID is always present, results can vary:

- Callback runs inline on the request thread: may see the request's MDC.
- Callback runs on a pooled worker: MDC is **not automatically copied** from the request thread.
- If a worker fails to clean up MDC properly, the callback might see a **stale trace ID** from an earlier task on that worker.

When correlation IDs are needed, pass them explicitly in payloads or use proper context propagation. With Spring's `ThreadPoolTaskExecutor`, a `TaskDecorator` can copy/restore context at submission time when needed, yet **never assume a decorator on an upstream executor covers every later non-async callback**. Inline callbacks on arbitrary threads do not pass through the configured executor's task decorator.

### 8.2. Transaction Context

Spring transactions are normally thread-bound. A non-async callback can run on the completion thread or registration thread; **do not rely on timing** to guess whether the caller's transaction is still active.

Example:

```java
@Transactional
public void createOrder() {
    CompletableFuture<String> f = remoteCallAsync();
    f.thenApply(result -> updateOrder(result));
}
```

This is a risky fragment: `thenApply` may execute on another thread outside `createOrder`'s transaction, or inline on the caller depending on completion timing. If `updateOrder` needs a transaction, place it on a **Spring-managed service method** with an explicit transaction boundary invoked through a proxy; never assume transactions "flow" into callbacks.

Even if a callback happens to run inline and see the transaction, that is not a durable design. In async pipelines, define transaction boundaries per data operation and ensure idempotency and consistency where needed.

### 8.3. Security/Request Context

`SecurityContextHolder` by default typically binds state to a thread. `RequestContextHolder` also carries assumptions about thread/request lifetimes. Do not push short-lived request objects or mutable request contexts into queues/continuations and access them long after the HTTP request finishes.

If identity is needed for background processing, pass the **verified, minimal identity data required**, or use wrappers/executors that support controlled context propagation. Do not blindly copy entire sensitive contexts across threads without understanding boundaries.

## 9. Blocking Callbacks Can Cause Starvation and Deadlock

Two anti-patterns to avoid:

### 9.1. Blocking the Completion Thread Waiting on Another Task in the Same Pool

```java
CompletableFuture<String> result =
        upstream.thenApply(value -> {
            // If downstream needs the worker held by this callback,
            // waiting can cause starvation.
            return nextAsync(value).join();
        });
```

This is an illustrative fragment. If the pool has only one worker and `nextAsync` must also be scheduled on that same pool, the callback holds the worker and calls `join` waiting for a task that cannot start: **starvation deadlock**.

Replace with composition:

```java
CompletableFuture<String> result =
        upstream.thenCompose(value -> nextAsync(value));
```

`thenCompose` does not block a thread merely waiting for the child stage. Even so, **the function initiating the child stage is still non-async** and can run on the completion thread; if initiating it is itself heavy, consider `thenComposeAsync(..., executor)`.

### 9.2. Blocking on Event Loops

With WebFlux/Netty and reactive/non-blocking libraries, the completion thread is sometimes an event-loop thread. A `thenApply` callback calling JDBC, `Thread.sleep`, or heavy CPU work can block the event loop and affect many connections. Use the offloading/scheduling mechanism appropriate for your framework and libraries; do not assume "Futures are async so blocking anywhere is fine."

### 9.3. Synchronous Callback Running Inline on the Caller

Even in traditional servlet MVC, `completedFuture(...).thenApply(this::slowStep)` can call `slowStep` inline at registration time, holding the request thread. Thus two identical requests with different upstream completion timings can experience **different latency at the join/chaining point**.

Do not use non-async methods for heavy work just because one test run showed the callback executing on a background worker.

## 10. Exceptions Are Completions Too; Error Handling Can Run Inline

A future can complete exceptionally:

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(new IllegalStateException("service down"));

CompletableFuture<String> recovered =
        source.exceptionally(error -> "fallback");
```

If `source` already completed exceptionally before registration, `exceptionally` may run immediately on the registration thread. When upstream is incomplete, a non-async fallback may run on the thread performing the exceptional completion.

An error callback making external DB/HTTP calls for fallback carries the same blocking risk as a success callback.

### Key Rules

- `thenApply` normally runs its action only when upstream completes normally; if upstream is exceptional, the dependent stage propagates the error per `CompletionStage` rules.
- `handle` receives both result and throwable; suited for transforming both success and failure.
- `whenComplete` suits logging/observability, yet can produce a failed dependent stage if the callback itself throws; it is not a tool to "swallow all exceptions."
- `exceptionally` can recover an upstream failure into a normal result by returning a fallback; **explicitly define** which fallbacks are acceptable by business rules.
- `join()` throws `CompletionException` on failure; `get()` can throw `ExecutionException`/`InterruptedException`. Observe the right error path.
- When using a custom executor, task scheduling may be **rejected** if the pool is overloaded or shutting down; never promise `thenApplyAsync` always succeeds just because it has the `Async` suffix.

In Spring, manage error paths for `@Async void` and `CompletableFuture<T>` separately: an uncaught async exception handler applies to `void`, whereas callers of a `Future` must observe exceptional completions via `whenComplete`/`handle` or proper framework error mapping.

## 11. Measurement, Testing, and Design Decisions

### 11.1. Testing Execution Threads Deterministically

A reliable test does not rely on `Thread.sleep(100)` and guess that a worker finished. Use:

1. An incomplete `CompletableFuture<String>`.
2. A `CountDownLatch` holding the completion worker before calling `complete`.
3. Register `thenApply` before opening the latch.
4. Record the thread name inside the callback, without tying business logic to fixed thread-name comparisons.
5. Open the latch and use `join`/`get` to await the result.
6. Compare against a `completedFuture` already completed prior to registration.
7. Register `thenApplyAsync(fn, executor)` on a named executor and verify isolated steps go through it.

The `ContinuationThreadDemo.java` demo above exercises the first three scenarios with verifiable output.

### 11.2. How to Choose Non-Async vs. Async

| Scenario | Recommendation |
| --- | --- |
| Very small value mapping, pure function, non-blocking | `thenApply` may be appropriate |
| Lightweight logging/metrics without `ThreadLocal` reliance | `whenComplete` may be appropriate |
| CPU-heavy transformation | `thenApplyAsync(fn, cpuExecutor)` |
| Blocking I/O inside callback | `thenCompose` with a genuinely async API, or `thenApplyAsync`/`thenComposeAsync` on an appropriate I/O executor |
| Registering callback in an HTTP request that must not block the request thread | Avoid heavy non-async callbacks; offload via an executor |
| Combining two Futures followed by heavy processing | `thenCombineAsync(..., executor)` |
| Calling a child API returning `CompletionStage<T>` | `thenCompose` to flatten; add Async if creating the stage needs dispatch |
| Business logic needs its own transaction | Call a Spring bean method with an explicit transaction boundary; do not rely on callback thread |
| Needs MDC/security context | Propagate context deliberately; never trust futures to inherit thread-locals |
| Project needs measurable quotas and latency | Bounded executor bean, metrics, overload policy, and lifecycle management |
| A previous stage used `thenApplyAsync` | Evaluate the next stage independently, since executors are not automatically "inherited" |

Choose based on **execution cost and resource boundaries**, not a blanket rule like "always Async is best" or "always non-Async is fastest." Dispatching too many tiny callbacks adds scheduling overhead; leaving large callbacks inline can choke completion workers.

### 11.3. Monitoring to Catch Callbacks Running in the Wrong Place

For Spring systems with multiple executors, monitor:

- Thread names when callbacks start, without **using thread names in business logic**.
- Per-continuation execution time and end-to-end latency.
- `ThreadPoolTaskExecutor#getActiveCount()`, `getPoolSize()`, and queue depth.
- Rates of rejected scheduling, exceptional completions, timeouts, and cancellations.
- Thread dumps during stalls to see whether completion workers are occupied by callbacks or waiting in `join`.
- HTTP request and event-loop latency when upstream finishes quickly, since callbacks may run inline on the caller.

An 800 ms callback is not "lightweight" just because it sits inside `thenApply`. Identifying which callback occupies which thread helps decide what to offload.

## 12. Common Pitfalls

**Pitfall 1 — Believing every `thenApply` runs on the thread that created the future.** The future may be completed on another thread, or already completed before callback registration.

**Pitfall 2 — Believing non-Async is guaranteed to run on the completion thread.** That is a common possibility, **not an absolute guarantee**; the callback can run immediately on the registration thread.

**Pitfall 3 — Believing `thenApplyAsync` always uses Spring's `@Async` executor.** Without passing an executor, `CompletableFuture` uses its default async facility, usually the common pool.

**Pitfall 4 — Offloading CPU work with `thenApplyAsync` but forgetting an explicit executor.** This can push computation onto the shared common pool, which is not monitored like a Spring pool.

**Pitfall 5 — Using `thenApply` to call blocking APIs or long computations.** Completion workers, request threads, or event loops may be held unexpectedly.

**Pitfall 6 — Chaining `thenApply` after `thenApplyAsync` and assuming the executor is "inherited."** Non-async continuations still carry no fixed thread guarantee.

**Pitfall 7 — Assuming `thenCompose` means "everything is asynchronous."** The callback creating the child stage can still run inline; only waiting on the child stage is flattened without blocking via `join`.

**Pitfall 8 — Calling `join()` inside a callback running on a single-thread executor.** If the awaited task needs that same worker, starvation deadlock can occur.

**Pitfall 9 — Relying on request `ThreadLocal`/transactions inside callbacks.** Completion threads vary with timing, and thread-locals do not automatically transfer across `CompletableFuture`.

**Pitfall 10 — Assuming `@Async` works when a method calls itself inside the same bean.** Self-invocation under default proxy mode bypasses the interceptor.

**Pitfall 11 — Ignoring exceptional completion.** A future may have ended in error, skipping `thenApply` callbacks while leaving endpoints unaware if the Future is ignored.

**Pitfall 12 — Creating a new executor per callback.** Causes thread leaks and loss of capacity control; prefer shared, managed executors.

**Pitfall 13 — Making every tiny callback Async unconditionally.** Increases scheduling overhead without improving throughput. Measure and choose boundaries that truly matter.

**Pitfall 14 — Testing with sleep and asserting a fixed execution thread.** Timing shifts across JVMs, machines, and loads; use latches and explicitly named executors in experiments, and still never bind production business logic to thread identity.

## 13. Self-Check Questions

**Question 1.** Does `CompletableFuture.completedFuture("x").thenApply(fn)` always run on a worker thread?

**Answer:** No. The future was already complete before registration, so in typical implementations `fn` may run directly on the thread calling `thenApply`.

**Question 2.** An `@Async("ioExecutor")` method returns `CompletableFuture<String>`. If you chain `thenApply(this::heavyCpu)`, will `heavyCpu` definitely run on `ioExecutor`?

**Answer:** No. A non-async callback may run on the completion thread or a registration/completion-related thread depending on timing. To route CPU work, use `thenApplyAsync(this::heavyCpu, cpuExecutor)`.

**Question 3.** Does `thenApplyAsync(fn)` without an executor automatically use Spring's default `ThreadPoolTaskExecutor`?

**Answer:** No. Per JDK `CompletableFuture` policy, it typically uses `ForkJoinPool.commonPool()`, not automatically a Spring bean.

**Question 4.** Does `thenApplyAsync(fn, directExecutor)` guarantee a different thread?

**Answer:** No. A direct executor like `Runnable::run` can execute the action directly on the caller of `execute`. "Async" is a scheduling mechanism via an executor, not a guarantee of creating or switching threads.

**Question 5.** Does `thenCompose(user -> fetchAsync(user))` block waiting for `fetchAsync`?

**Answer:** No. It merges the child stage into the result stage. However, the callback initiating `fetchAsync` is non-async and may run on the completion thread.

**Question 6.** Why should you avoid `thenApply(x -> fetchAsync(x).join())` on a small pool?

**Answer:** The callback can hold a worker and block waiting on a child task that also needs that worker, causing starvation or deadlock. Normally use `thenCompose(x -> fetchAsync(x))`.

**Question 7.** Is it safe if a `whenComplete` callback only logs?

**Answer:** It can be suitable if genuinely lightweight, non-blocking, and independent of unpropagated context. If logging/telemetry does slow I/O or needs special context, re-evaluate where it runs.

**Question 8.** A non-async callback happened to see the caller's transaction/request MDC in one test. Should you rely on that?

**Answer:** No. If the future completes at a different time, the callback can run on another thread missing that context. Design transactions, security, and correlation explicitly across boundaries.

**Question 9.** A `thenApplyAsync(..., cpuExecutor)` step has completed. Where will a `thenApply(...)` attached afterward run?

**Answer:** It may run inline on the registering thread because upstream is already complete; if registered before upstream finishes, it may run on the thread completing the stage. There is no "always CPU executor" rule.

## Summary

- **Non-Async continuations carry no guaranteed thread affinity.** They may run on the completion thread or another thread participating in completion; if upstream already has a result, they may run right at registration time.
- **The `Async` suffix requests scheduling**, yet does not guarantee a "new thread"; when clear resource boundaries are needed, pass an **explicit executor**.
- **Spring `@Async` dispatches only proxy-intercepted methods**, without attaching that executor bean to every `CompletableFuture` continuation.
- Keep only small, pure, non-blocking callbacks non-async when appropriate. **Offload heavy CPU work, blocking I/O, or steps requiring isolation** to a suitable executor.
- Avoid blocking `join()` inside completion callbacks; use `thenCompose` for child stages. Never rely on `ThreadLocal`, MDC, transactions, or thread names coinciding due to timing.
- Verify with tests using `CountDownLatch`, explicit executors, and callback latency measurements instead of drawing conclusions from a single arbitrary run.

## References

1. Java SE 17 API — CompletableFuture, asynchronous completion policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
2. Java SE 17 API — CompletionStage methods: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
3. Java SE 17 API — Executor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
4. Spring Framework Reference — Task Execution and Scheduling, `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
5. Spring Framework Javadoc — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
6. Spring Framework Reference — AOP proxying and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
