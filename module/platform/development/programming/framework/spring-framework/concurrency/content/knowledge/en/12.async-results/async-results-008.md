# Do Not Call get() or join() Immediately When the Goal Is Overlapping Work

## 1. The Problem: Having a Future Yet Still Running Sequentially

In Spring Framework, a method annotated with `@Async` can run on a `TaskExecutor` and return `Future<T>` or `CompletableFuture<T>`. However, **asynchrony on the worker side does not mean the caller is taking advantage of concurrency**. If after every call you immediately wait for the result with `get()` or `join()`, the caller stops at that wait point and **never gets around to submitting the next independent task**.

An example mistakenly thought to be parallel:

~~~java
String inventory = inventoryService.loadAsync().join();
String price = pricingService.loadAsync().join();
return inventory + " / " + price;
~~~

This is an **illustrative code snippet**, assuming both service beans genuinely return `CompletableFuture<String>` from valid `@Async` methods. The first statement submits the inventory request and **waits for it to finish**; only afterward does it call pricing. Two independent operations are not started together.

Replace with:

~~~java
CompletableFuture<String> inventory = inventoryService.loadAsync();
CompletableFuture<String> price = pricingService.loadAsync();

return inventory.thenCombine(price, (stock, amount) ->
        stock + " / " + amount);
~~~

The second snippet assumes the enclosing method returns `CompletableFuture<String>`. It **submits both tasks first**, and then builds a future of the combined result. The caller does not need to block at each submission. In practice, the two tasks can only overlap when the executor, resources, locks, and downstream allow it; `CompletableFuture` does not by itself guarantee multiple workers are running concurrently.

**Core rule:** if tasks are independent, **start all work that should run concurrently first**, and only then **coordinate results or wait at the boundary where the result is genuinely needed**. Do not eliminate waiting entirely; simply place the wait point in the right spot.

## 2. Distinguishing Three Moments: Submit, Execution, and Await

~~~text
Time ----------------------------------------------------------------->

Easy way to accidentally serialize:
Caller:  submit A |====== get(A) ======| submit B |==== join(B) ====|
Worker:      [------- A -------]                  [------ B ------]

Way that allows overlapping:
Caller:  submit A -> submit B -> do work C -> combine -> | wait if needed |
Worker 1:    [------- A --------]
Worker 2:         [---------- B ---------]
Caller C:              [-- C --]
~~~

The diagram above only illustrates where blocking occurs; actual durations depend on task length, thread availability, and scheduling. Two consecutive submit operations **do not strictly** lead to two threads running simultaneously. They may sit in a queue if the pool lacks capacity.

### 2.1. When Does Each Action Happen?

| Action | What happens? | Does the caller block waiting for the result? |
| --- | --- | --- |
| `worker.workAsync()` through Spring proxy | Interceptor submits execution to executor and returns a result handle | Normally **does not wait** for method body to finish, though submission can still be affected by saturation/rejection |
| `CompletableFuture.supplyAsync(task, executor)` | Submits task to specified executor | Does not wait for task completion when submission succeeds |
| `future.get()` | Waits for completion, returns value or throws corresponding exception | **Yes** if not yet done |
| `future.join()` | Waits for completion, returns value or throws unchecked completion exception | **Yes** if not yet done |
| `future.thenApply(fn)` | Registers a transformation step after prior future finishes | Does not force caller to wait, though callback may run immediately on caller if future is already complete |
| `future.thenCompose(fn)` | Chains a next step returning another future | Does not force caller to wait at each step; there is a **data dependency** between the two steps |
| `a.thenCombine(b, fn)` | Creates combined future when **both a and b** succeed | Does not force caller to wait immediately |
| `CompletableFuture.allOf(...)` | Creates future completing when all input futures complete | Does not block at registration time |
| `get(timeout, unit)` | Blocks, yet with a wait time limit | Yes; can throw `TimeoutException` |

**Important point:** `get` and `join` are not wrong APIs. They are appropriate when the caller **genuinely must synchronize** at the end of processing, in tests/CLIs, or at a result-returning boundary. The mistake lies in **waiting too early while independent work has not been submitted yet**.

## 3. Why Does Immediate Waiting Lose the Chance to Overlap?

Suppose there are two independent I/O calls: A typically takes around 400 ms, B typically takes around 600 ms; durations are for illustration only, not guarantees.

Sequential approach:

~~~java
Result a = service.fetchAsync("A").join(); // wait for A
Result b = service.fetchAsync("B").join(); // only now submit B
consume(a, b);
~~~

Total wait time can approach **400 + 600 ms**, excluding overhead. Even though `fetchAsync` genuinely runs on workers, the caller never gives B a chance to start while A is running.

Better approach:

~~~java
CompletableFuture<Result> aFuture = service.fetchAsync("A");
CompletableFuture<Result> bFuture = service.fetchAsync("B");

// Caller can continue processing other work not depending on the results.
prepareResponseMetadata();

// Synchronize only when both are needed:
Result a = aFuture.join();
Result b = bFuture.join();
consume(a, b);
~~~

This snippet is a conceptual example, needing `Result`, `service`, `prepareResponseMetadata`, and `consume` in the application. If the executor has sufficient capacity and the two tasks do not lock each other out, completion time can approach `max(400, 600)` rather than the sum, though **this must not be treated as a performance guarantee**.

If you do not want the caller to block at the end, let the orchestration function **return `CompletableFuture`**:

~~~java
public CompletableFuture<CombinedResult> getCombined() {
    var a = service.fetchAsync("A");
    var b = service.fetchAsync("B");
    return a.thenCombine(b, CombinedResult::new);
}
~~~

This is an illustrative method, needing `CombinedResult`, `service`, Spring configuration, and imports. When downstream consumers also accept a Future, we can **maintain an asynchronous pipeline** across multiple layers. If a final layer is forced to return a synchronous value, wait only at **that layer**, with timeouts and error handling.

## 4. get() and join(): Same in Blocking, Different in Error Reporting

### 4.1. Future.get()

With `java.util.concurrent.Future<T>`:

~~~java
T result = future.get();
T resultWithTimeout = future.get(3, TimeUnit.SECONDS);
~~~

The two lines are **alternative** usages, not placed in the same scope due to overlapping variable names. `get()` can block indefinitely; `get(timeout, unit)` bounds the wait time. Common checked exceptions include:

- `InterruptedException`: the waiting thread was interrupted; if caught for cleanup, restoring the interrupt flag is usually appropriate.
- `ExecutionException`: the task completed with an error; `getCause()` can be inspected.
- `TimeoutException`: the wait time exceeded the limit.
- `CancellationException`: the Future was cancelled (unchecked).

`get(timeout)` throwing `TimeoutException` **does not mean the task stopped**; work may still be running and continuing to affect the system. Caller timeouts, cancellation, job status, and downstream impact must be handled per business rules.

### 4.2. CompletableFuture.join()

`CompletableFuture<T>.join()` also blocks if the future is not yet complete, yet does not force the caller to declare/catch checked `InterruptedException` or `ExecutionException`:

~~~java
String value = future.join();
~~~

If the Future fails, `join()` typically throws `CompletionException` (unchecked) wrapping the cause; if cancelled, it can throw `CancellationException`. `join()` **has no direct timeout parameter**. With a `CompletableFuture` needing a timeout, you can use `get(timeout, unit)`, or consider `orTimeout`/`completeOnTimeout` per the API contract.

**Do not conclude `join()` is "non-blocking" just because it declares no checked exceptions.** Both `get()` and `join()` can block the thread at the call site.

### 4.3. What If the Future Has Already Completed?

When a future has already finished, `get()` and `join()` can return immediately or throw immediately; they do not necessarily add delay. The advice "do not wait immediately" primarily aims to avoid holding the caller before **all potentially independent tasks have been started** or when on a thread that should not block.

## 5. Three Proper Coordination Patterns

### Pattern A — Submit First, Wait Later (fork-then-join)

~~~java
CompletableFuture<Customer> customer = customerClient.getAsync(id);
CompletableFuture<Orders> orders = orderClient.listAsync(id);

// Work independent of customer/orders.
AuditMetadata metadata = buildMetadata();

Customer c = customer.join();
Orders o = orders.join();
return assemble(c, o, metadata);
~~~

This illustrative snippet **deliberately places join points** at the end, after starting both tasks. It fits when the function must return a synchronous value and the caller thread **is allowed to wait**. If the caller is a request thread, review timeouts, load, and how the web framework handles async processing.

### Pattern B — Combine Results Without Blocking the Caller

~~~java
public CompletableFuture<Overview> getOverview(String id) {
    var customer = customerClient.getAsync(id);
    var orders = orderClient.listAsync(id);
    return customer.thenCombine(orders, Overview::new);
}
~~~

This illustrative code fragment requires the declared types and beans. `thenCombine` runs when **both** complete successfully, without needing the caller to call `join`. It is the way to express "once both results are ready, perform the next step."

**Note on callback execution thread:** `thenCombine` without the `Async` suffix usually executes the callback on the thread completing one of the stages, or on the registering thread if stages are already done. If the combining step performs heavy CPU work or blocking I/O, consider `thenCombineAsync(fn, chosenExecutor)`, while avoiding saturating the exact pool needed to run the remaining tasks.

### Pattern C — Multiple Futures with allOf()

~~~java
List<CompletableFuture<String>> futures = List.of(
        service.runAsync("A"),
        service.runAsync("B"),
        service.runAsync("C"));

CompletableFuture<List<String>> results =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0]))
                .thenApply(ignored ->
                        futures.stream()
                                .map(CompletableFuture::join)
                                .toList());
~~~

This illustrative fragment requires `List`, `service`, and appropriate imports. Here:

1. Three methods are called first, creating three Futures.
2. `allOf` creates a Future finishing when **all** input Futures finish.
3. `thenApply` only runs normally after `allOf` succeeds; by then, the `join()` calls to extract values **no longer wait on tasks**.
4. If any Future completes with an error, `allOf` usually completes with an error and the `thenApply` callback does not run. Errors must be handled in the pipeline if partial results are needed.

`allOf()` **does not itself produce a `List<T>` of results**; it returns `CompletableFuture<Void>`. The result-collection step must be written separately. Never put `join` inside a loop **that builds the list of Futures** like "submit one item and wait immediately," because that turns the process back into sequential execution.

## 6. Distinguishing Independent Work from Dependent Work

Not every early `join` is unreasonable; rather, if B **needs A's result as input**, B cannot genuinely start before A exists:

~~~java
// A completes first so we know the key to fetch B.
CompletableFuture<Account> account = accountService.findAsync(userId);

CompletableFuture<Profile> profile =
        account.thenCompose(a -> profileService.loadAsync(a.profileId()));
~~~

This illustrative code fragment uses `thenCompose` because the callback returns another Future. `thenApply` in this case would produce `CompletableFuture<CompletableFuture<Profile>>` instead of flattening the result. **`thenCompose` does not create parallelism between A and B**, since B truly depends on A; yet it keeps the orchestration from blocking a thread while waiting.

In a workflow with tasks A, B, C, and D:

- A and B are **independent**: both can be submitted immediately.
- C **depends on A+B results**: use `thenCombine` or `allOf` to trigger C once all data is ready.
- D is **unrelated**: can be submitted before or while A/B are running.

This mindset builds a **dependency graph** instead of mechanically waiting line by line.

~~~text
A ─────────┐
           ├──> C (needs A and B) ───> result
B ─────────┘
D ──────────────────────────────────> independent work
~~~

Only **truly dependent** edges force waiting; independent parts gain the opportunity to overlap.

## 7. Standalone Spring Demo: Observing Both Tasks Start Before the Caller Waits for Results

This example is designed to **verify behavior**, not guess by timing speed. It uses **Java 17+, Spring Framework 6.1.14, and Gradle 8.5+**, without needing Spring Boot, an HTTP server, or a database.

Two `@Async` method calls run on a `ThreadPoolTaskExecutor` with **two workers**. Both workers signal via a `CountDownLatch` once started, then wait together on another latch. The caller starts **both** first, performs an independent computation, observes both workers have entered the method, and only then lets them finish.

### 7.1. Project Structure

~~~text
overlap-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/OverlapDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'overlap-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.OverlapDemo'
}
~~~

**src/main/java/demo/OverlapDemo.java**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class OverlapDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JobWorker worker = context.getBean(JobWorker.class);

            CountDownLatch bothStarted = new CountDownLatch(2);
            CountDownLatch release = new CountDownLatch(1);

            // Submit both tasks before retrieving any result.
            CompletableFuture<String> a =
                    worker.workAsync("A", bothStarted, release);
            CompletableFuture<String> b =
                    worker.workAsync("B", bothStarted, release);

            // Create combined future without blocking caller here.
            CompletableFuture<String> combined =
                    a.thenCombine(b, (left, right) ->
                            left + "+" + right);

            try {
                // Caller continues processing independent work.
                int callerComputation = 20 + 22;
                System.out.println("caller work: " +
                        (callerComputation == 42));

                // Wait for test SIGNAL: both workers entered the method.
                if (!bothStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Two tasks did not start in time");
                }
                System.out.println("both tasks started: " +
                        (bothStarted.getCount() == 0));

                // Workers cannot finish yet because they wait on release.
                System.out.println("both futures pending: " +
                        (!a.isDone() && !b.isDone()));

                release.countDown();

                // Final synchronization point: result is needed now.
                System.out.println("combined result: " +
                        combined.get(5, TimeUnit.SECONDS));
                System.out.println("both futures completed: " +
                        (a.isDone() && b.isDone()));
            } finally {
                // Avoid wedging workers if test/observation fails.
                release.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("overlap-worker-");
            return pool;
        }

        @Bean
        public JobWorker jobWorker() {
            return new JobWorker();
        }
    }

    public static class JobWorker {
        @Async("workerExecutor")
        public CompletableFuture<String> workAsync(
                String name,
                CountDownLatch started,
                CountDownLatch release) {

            started.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    return CompletableFuture.failedFuture(
                            new IllegalStateException(
                                    "Release latch timed out"));
                }
                return CompletableFuture.completedFuture(
                        name + "-done");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }
        }
    }
}
~~~

**Run** in the `overlap-demo` directory:

~~~bash
gradle run
~~~

If a Gradle Wrapper is present, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

**Stdout lines printed by the program itself**, when both workers start and finish normally within the five-second threshold:

~~~text
caller work: true
both tasks started: true
both futures pending: true
combined result: A-done+B-done
both futures completed: true
~~~

Spring or Gradle logs may appear in addition to these five lines. The demo **does not assert latency** or specific thread-name suffixes. If the environment lacks resources and workers fail to start within the timeout, the program throws an exception instead of treating it as a successful result.

### 7.2. Why Does the Demo Verify Overlap?

1. `Config` enables `@EnableAsync`; `JobWorker` is created by the container and `workAsync` is called from code outside the bean through the Spring proxy.
2. `workerExecutor` has two workers and accepts both tasks A and B.
3. Each worker decrements `bothStarted` and then waits on `release`. Reaching `bothStarted == 0` **can only happen when both methods have started running**, not merely sitting in the queue.
4. When the caller checks `both futures pending`, neither worker has been released, so both `CompletableFuture`s remain unfinished.
5. The caller releases the latch; both workers finish. The `combined` Future completes automatically once both A and B have results; the caller only calls `get(timeout)` at the boundary needing to print the result.
6. Changing the code to `worker.workAsync("A", ...).get()` **before** submitting B would make the caller wait for A while A waits on `release`; it would never even reach submitting B in the example's sequence. That test scenario clearly shows how waiting too early destroys overlap opportunities.

`CountDownLatch` here serves **controlled testing**, not a requirement to have latches in every `@Async` program. In production, real tasks usually wait on I/O, process CPU work, or coordinate with external systems; `CompletableFuture`/Future reflects completion state.

## 8. Applying to Spring Services and Controllers

### 8.1. Service Layer Returns a Future Instead of Waiting Internally

Avoid writing a synchronous method with two early `join`s returning a value:

~~~java
public DashboardData loadDashboard() {
    var account = accountService.getAsync().join();
    var orders = orderService.listAsync().join();
    return new DashboardData(account, orders);
}
~~~

Instead, if the API can be asynchronous:

~~~java
public CompletableFuture<DashboardData> loadDashboardAsync() {
    var account = accountService.getAsync();
    var orders = orderService.listAsync();
    return account.thenCombine(orders, DashboardData::new);
}
~~~

Both methods above are **illustrative code fragments**, requiring corresponding dependencies/services/data types. The calling layer decides when to await. When applying `@Async` to service methods, remember **self-invocation** in default proxy mode does not trigger interception; inject a Spring-managed worker bean and call through the proxy.

### 8.2. In Spring MVC

A controller can return `CompletableFuture` or an async result type supported by MVC, letting Spring manage the async request boundary. Choose a mechanism compatible with return types, timeouts, and MVC configuration.

Illustrative snippet (requires `spring-webmvc`, imports, and appropriate beans):

~~~java
@RestController
class DashboardController {
    private final DashboardService service;

    DashboardController(DashboardService service) {
        this.service = service;
    }

    @GetMapping("/dashboard")
    public CompletableFuture<DashboardData> dashboard() {
        return service.loadDashboardAsync();
    }
}
~~~

The main point is not calling `service.loadDashboardAsync().join()` right inside the controller if the goal is **freeing the request thread**. However, a Future return type **does not create infinite execution capacity**; timeouts, max async request limits, queue/rejection policies, and downstream connections are still required.

An HTTP request still ultimately needs a result to respond. **Not blocking in the controller** differs from **never having to wait for the result**: MVC can manage waiting/dispatching via its asynchronous request processing mechanism. Never casually use Future to hide an internal blocking operation without evaluating resources.

### 8.3. In Scheduled Jobs or Message Consumers

A scheduled task can submit independent subtasks and coordinate results with Futures, yet watch callback lifecycles: if the scheduler callback blocks on `join()` for a long time, it can hold the scheduler thread, delaying other triggers. If the callback submits and returns immediately, subsequent schedule ticks may **overlap background work**; deduplication or capping active jobs is needed if business rules forbid overlap.

With message listeners, do not just submit asynchronously and **acknowledge the message immediately** if the system requires successful processing before ack. Where to wait or send ack depends on the delivery contract. In-memory `@Async` and Futures do not guarantee recovering tasks after a process crash.

## 9. Handling Errors, Timeouts, and Cancellation Without Breaking Asynchrony

### 9.1. Handling Errors in a Future Chain

~~~java
CompletableFuture<String> safe = worker.workAsync()
        .exceptionally(error -> {
            logFailure(error);
            return "fallback";
        });
~~~

This is an illustrative fragment requiring a `worker` bean, `logFailure` method, and matching return type. `exceptionally` creates a stage supplying a replacement value when the prior stage completes with an error; **it does not automatically retry** failed work nor guarantee rolling back side effects.

To merely observe errors while preserving exceptional status:

~~~java
CompletableFuture<String> observed = worker.workAsync()
        .whenComplete((value, error) -> {
            if (error != null) {
                logFailure(error);
            }
        });
~~~

The callback in `whenComplete` does not turn failure into success on its own. With combined stages, explicitly define whether one branch failing aborts the whole operation, uses a fallback, or yields partial results.

### 9.2. Using Timeouts for the Right Purpose

~~~java
CompletableFuture<String> task = worker.workAsync();
String value = task.get(3, TimeUnit.SECONDS);
~~~

This example **deliberately waits** up to three seconds at the result-requiring boundary. A `get(timeout)` expiration **does not automatically stop the task**. If the caller must return HTTP within a threshold, decide how to handle still-running tasks, cancellation, retries, and idempotency.

With `CompletableFuture`:

~~~java
CompletableFuture<String> timed = worker.workAsync()
        .orTimeout(3, TimeUnit.SECONDS);
~~~

`orTimeout` can **exceptionally complete the received CompletableFuture itself** after timeout; it does not necessarily cancel the actual computation running under the executor. `completeOnTimeout` substitutes a default value if not yet done. Never use timeouts as a substitute for admission control or task cancellation.

### 9.3. Do Not Abandon Futures

Avoid "ownerless fire-and-forget":

~~~java
worker.sendAsync(data); // neither saves handle nor handles errors/ack
~~~

The illustrative fragment above is **not wrong by default**, yet for tasks with business value, the caller should have a way to record status, track failures, or retry. With `@Async void`, exceptions from the worker cannot be rethrown synchronously to the caller; configure `AsyncUncaughtExceptionHandler`, logs, and metrics. If the operation must survive restarts, use a durable job store, outbox, or broker instead of keeping Futures only in heap.

## 10. Overlap Depends on Resources, Not Just Invocation Style

Not calling `join` immediately **only creates the opportunity** for concurrent execution. Other constraints still apply:

| Constraint | Impact |
| --- | --- |
| Executor has only one worker | A and B usually run one after another even if submitted together |
| Pool queue is full | Tasks are rejected; handlers like DiscardPolicy may silently drop tasks |
| Pool uses CallerRunsPolicy | When saturated, the caller may run the task immediately, blocking the submit call |
| Two tasks contend on the same lock | Only one task enters the critical section at a time |
| DataSource pool has one connection | Two workers may wait on the same resource; throughput does not increase |
| Downstream rate/connection limits | Parallel sending may increase 429/503 errors or timeouts |
| CPU-bound workload on few cores | Adding too many workers can increase context switching and slow things down |
| Task bound to transaction/ThreadLocal | Moving to a worker can lose required context if not propagated properly |

**Executor configuration must be purposeful.** In `ThreadPoolTaskExecutor`, `corePoolSize`, `maxPoolSize`, `queueCapacity`, and the rejection handler interact with one another. A large queue can absorb many requests while increasing latency and memory. A pool with too few workers will not let A/B overlap even though the orchestrator submitted both.

Adding threads does not turn blocking I/O into non-blocking I/O and does not automatically make singleton classes thread-safe. Spring Boot's `spring.task.execution.*` properties only apply under corresponding auto-configuration rules; plain Spring Framework apps in demos do not read these Boot properties.

### 10.1. Risk of Thread Starvation Deadlock When Waiting on a Future Inside a Pool

Example assuming an executor with only **one worker** and a queue with space:

~~~java
executor.execute(() -> {
    Future<String> child = executor.submit(() -> "child result");
    String result = child.get(); // sole worker waits on child
    use(result);
});
~~~

This snippet is for illustration only (needs enclosing checked-exception handling, `executor`, and `use`). The parent task occupies the worker and waits on the child. Yet the child sits in the queue needing that very worker to run: **thread starvation deadlock**. Having a timeout lets the parent stop waiting; it does not make this waiting design optimal.

To reduce the risk, express pipelines via continuations, avoiding blocking a worker while waiting for another task running on the same constrained pool. If steps depend purely sequentially, sometimes **calling directly on one worker** is simpler than submitting a child and waiting. Size pools, queues, and dependency graphs together.

## 11. Transactions, Context, and Singletons When Overlapping Work

In Spring, a caller's `@Transactional` is typically bound to **the current thread**. When `@Async` uses another worker, the transaction context **is not automatically transferred**. Two concurrent async queries may also need two independent database connections/transactions. A request that writes data in an uncommitted transaction and immediately submits a worker to query it may encounter invisible data.

Do not hold a long transaction on the request thread just to wait on multiple Futures without a clear reason. For operations that must occur after commit, consider after-commit events or a transactional outbox depending on consistency and durability needs.

`ThreadLocal`s such as MDC, SecurityContext, and request attributes likewise do not propagate automatically across thread pools; use capture/restore mechanisms or an appropriate `TaskDecorator` when needed. Never embed sensitive user data into thread names to trace tasks; use structured logging/tracing instead.

A default singleton Spring `@Service` can be invoked concurrently by multiple workers. Avoid storing request-specific mutable fields on beans; pass immutable DTOs/records or snapshots and use proper synchronization for shared mutable state. Changing how Futures are coordinated does not eliminate data races on its own.

## 12. Verifying Effectiveness and Writing Stable Tests

### 12.1. Measure the Right Things

Do not compare single-run timings alone, because JVM warmup, caches, scheduling, network, and downstream latency make measurements fluctuate. Observe:

- **Task submit time** and number of submitted tasks.
- **Worker start/finish timestamps** to confirm execution intervals truly overlap.
- **Queue wait time**, active threads, queue depth, and rejections.
- **Caller blocked time** at `get()`, `join()`, or other wait points.
- **End-to-end response time** and cost imposed on external systems.

Two Futures created close together do not prove workers ran concurrently. The demo in section 7 uses a `CountDownLatch` to verify **both methods entered workers before being released** — stronger evidence than random timing measurements.

### 12.2. Test Abnormal Cases

1. One of two tasks throws an error: combined future may complete with error; assert the right cause.
2. One branch is very slow: apply timeouts and decide whether the other branch continues or gets cancelled.
3. Executor has only one worker: do not assert actual parallelism without capacity.
4. Executor rejects tasks: there must be a failure signal or fallback per contract.
5. Caller is interrupted during `get()`: handle interrupts properly without equating them to task failure.
6. One task depends on another: use `thenCompose`, do not try running the dependent branch before its input data exists.
7. High load: verify concurrency bounds, response timeouts, and queued task counts.
8. Long-lived job state: test job store, restarts/retries, and idempotency.

### 12.3. Verify @Async Actually Runs Through Spring

If calling an `@Async`-annotated method runs synchronously, check again:

- Is `@EnableAsync` enabled in the right `ApplicationContext`?
- Is the worker Spring-managed and does the caller inject the proxy from the container?
- Is there self-invocation `this.asyncMethod()` inside the same bean?
- Can the method be intercepted by the Spring proxy (in practice, public and non-final)?
- Does `@Async("executorName")` point to the right executor bean?
- Is the caller calling `join()` immediately so it **looks** like the whole chain is synchronous even though the method is async?

Distinguish **annotation not active** from **annotation active yet wait point placed too early**; the fixes are completely different.

## 13. Anti-Patterns and Quick Fixes

| Anti-pattern | Consequence | Replace with |
| --- | --- | --- |
| `aAsync().join(); bAsync().join();` when A/B are independent | B never starts before A finishes | Create Futures A and B first, wait or combine later |
| `future.get()` directly inside an HTTP controller | Holds the request thread waiting | Return Future/appropriate MVC async type, configure timeouts |
| `stream.map(item -> async(item).join())` | Submits and waits item by item, becoming nearly sequential | `map(async)` to a list of Futures, then `allOf` |
| `CompletableFuture.supplyAsync(task)` without specifying a pool | Uses ForkJoin commonPool, ignoring custom Spring pool | `supplyAsync(task, explicitExecutor)` or Spring-managed `@Async` |
| `allOf(...)` while forgetting to extract individual results | Leaves only `CompletableFuture<Void>` | `thenApply` extracting results after `allOf` completes |
| `join()` inside a worker submitting a child to the same single-thread pool | Risks starvation/deadlock | Use continuations or reconfigure dependencies and pools |
| Creating thousands of Futures and calling unbounded `allOf` | Overloads pool, DB, network, or memory | Bounded concurrency, pagination, rate limits |
| Never observing Futures after dispatch | Background errors go unhandled | Error handlers, status, metrics, tracing |
| `get(timeout)` assuming the task stopped | Task can keep running after timeout | Define cancel/timeout at work and downstream layers |
| Treating `CompletableFuture` as a guarantee of surviving restarts | Future lives only in the process | Durable queue, outbox, or job store |

## 14. Refactoring Workflow from Early Waiting to Proper Coordination

**Step 1.** Draw the dependency graph: which tasks are independent, which need a prior task's result? Do not force parallelism on operations with mandatory ordering.

**Step 2.** Verify async infrastructure: `@EnableAsync`, managed worker bean, proxy invocation, executor, and queue capacity. If `@Async` is not active, fix that before optimizing `join`.

**Step 3.** Replace submit-then-immediately-wait code with **starting all independent branches first**:

~~~java
var a = workerA.calculateAsync();
var b = workerB.calculateAsync();
~~~

This is an illustrative snippet, assuming both return `CompletableFuture` and are properly invoked from a Spring-managed bean.

**Step 4.** If the caller must return a synchronous result, wait at the latest reasonable boundary; if async return is possible, **return the Future pipeline**:

~~~java
return a.thenCombine(b, Aggregate::new);
~~~

**Step 5.** Choose timeouts, exception handling, cancellation, and retries. Specifically, never ignore worker errors.

**Step 6.** Set concurrency limits based on CPU, connection pools, downstream rate limits, and latency targets; do not use async to turn overload into unbounded queues.

**Step 7.** Test with latches or instrumentation to confirm workers genuinely overlap and final results are correct. Also measure request latency, queue wait, and errors/rejections.

## 15. Self-Check Questions

1. **Why can calling `get()` right after `@Async` make two independent tasks A and B run sequentially?** Because the caller waits for A to finish before getting a chance to submit B.
2. **Is `join()` more non-blocking than `get()`?** No. Both can block; they differ mainly in exception/API style.
3. **Does switching from `get` to `join` create overlap on its own?** No; you must move the wait point and actually submit independent branches first.
4. **Is submitting two Futures first and calling `join` at the end valid?** Yes, when the caller is allowed to synchronize at that point and timeouts/errors are accounted for.
5. **Why is `thenCombine` suitable for two independent tasks?** It produces the result when both finish without forcing the caller to wait at registration time.
6. **When B depends on data returned by A, which API fits?** `thenCompose`, because the callback returns a Future and the dependency is real.
7. **Does `allOf` directly return a list of values?** No; it returns `CompletableFuture<Void>`, requiring a result-gathering step.
8. **Does having two Futures guarantee two workers run simultaneously?** No. It depends on the executor, queue, locks, and downstream.
9. **If `Future.get(timeout)` throws `TimeoutException`, has the task stopped?** Not necessarily; a wait timeout does not auto-cancel the computation.
10. **Why can waiting on a Future inside a single-thread pool worker deadlock?** If the worker is waiting on a child task that also needs that exact same worker to run.
11. **In Spring MVC, why is returning `CompletableFuture` often better than `join` in a controller?** It allows the framework to manage the async request instead of holding the request thread waiting synchronously, when the mechanism is compatible.
12. **Does offloading `@Async` to an executor automatically transfer transactions and `ThreadLocal`s?** No; explicit context/transaction design is needed.
13. **How do you prove overlap instead of just checking timings?** Control synchronization with latches or measure exact intervals of both workers; section 7's demo verifies both started before being released.
14. **Should `join` be avoided everywhere?** No. It is necessary at certain synchronous boundaries; what to avoid is **waiting too early** and **waiting on sensitive threads when better options exist**.

**Remember:** `@Async` helps **dispatch work**, while `CompletableFuture` helps **coordinate results**. To give independent tasks a chance to overlap, **submit them first**, **do not call `get()`/`join()` right after each submission**, and wait only where results are truly needed. At the same time, control executors, errors, timeouts, and resources — async does not automatically guarantee performance or work durability.

### Official Documentation

- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Async Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.1 — @Async API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
