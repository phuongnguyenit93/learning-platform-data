# void Is Suitable When the Caller Does Not Need to Receive a Direct Result

In asynchronous programming with Spring Framework, there are tasks where the caller only needs to **request execution**, without needing to directly receive a result value from that call. For example: proactively warming a regenerable cache, collecting auxiliary statistics that do not affect the main transaction, or updating a component for performance optimization. For the right kind of work, an `@Async` method with a `void` return type is a simple choice with clear intent.

However, **`void` only states that the method does not return a value**. It does not mean the method automatically runs asynchronously, has completed successfully, guarantees durable processing, or cannot throw errors. To execute asynchronously with Spring, the call must go through the `@Async`/`TaskExecutor` mechanism properly.

This lesson explains when to choose `void`, how it differs from `Future`/`CompletableFuture`, how `@Async void` error handling works, operational limits, and a standalone Java 17 example.

## 1. Understanding the True Meaning of void

A normal Java method:

~~~java
public void updateLocalState() {
    System.out.println("Updated");
}
~~~

does not return a result object. But **it still runs synchronously** on the calling thread until the method returns or throws an exception. Merely changing the return type to `void` does not create a new worker and does not reduce caller wait time.

The Spring method:

~~~java
@Async("backgroundExecutor")
public void warmCache(String key) {
    // Work runs in the executor if the call is properly intercepted by Spring.
}
~~~

is an **illustrative snippet placed inside a Spring-managed bean**. When called from outside the bean through the Spring proxy under an appropriate `@EnableAsync` configuration, the interceptor wraps the call into a task and submits it to the selected executor. The caller does not receive a `Future` from a `void` method, so there is no returned handle to `get()`, `join()`, `cancel()`, or read exceptions from.

There are three things to separate:

- **No need for return data:** the caller does not use the computed value of the task. This is a valid reason to consider `void`.
- **No need to know when it finishes:** the caller does not need to wait for the result immediately in the current control flow. This may be a second reason, but the system still needs operational-level monitoring.
- **No need for processing guarantees:** is an **entirely different** requirement. `@Async void` does not by itself determine durability, retries, or task criticality. The business logic may still need tracking mechanisms, state persistence, or a durable queue.

The term "fire-and-forget" is often used for the call-without-waiting model. It describes the behavior of the **caller**, not a guarantee that the task will complete, that errors are self-healing, or that work cannot be lost.

## 2. When Is void a Suitable Choice?

| Case | Suitability | Reason |
| --- | --- | --- |
| Warming a cache that can be regenerated when needed | **Usually suitable** | Caller does not need a direct value; task can be retried when needed |
| Computing auxiliary metadata that can be skipped under overload | **Potentially suitable** | Does not determine main transaction outcome, though errors still need to be measured |
| Sending non-critical notifications where best-effort is acceptable | **Potentially suitable** | API does not need to wait for sending to finish; still requires error, load, and retry policies |
| Recording a business event that must be durably stored | **Should not rely solely on in-memory @Async void** | Losing tasks on crash/shutdown can cause business inconsistency |
| Payments, debiting funds, or inventory updates that must succeed | **Unsuitable for simple fire-and-forget** | Requires state, idempotency, controlled retries, and confirmation capability |
| Caller needs to return a result after processing | **Unsuitable** | Needs a handle or another mechanism to return status/results |
| Caller needs to know whether the task failed or completed | **Typically use CompletableFuture<Void> or a job id** | No business payload returned, yet completion status is still needed |

A useful rule of thumb: **"not needing a return value" does not mean "not needing accountability for the outcome."** For important work, even when the caller does not wait directly, you can combine a queue/job store and a status lookup endpoint. Choose `void` based on the required contract between the caller and the task, not merely because you want the API to return a fast response.

## 3. Comparing void, Future, and CompletableFuture

In Spring, an `@Async` method typically declares a return type of `void` or a `Future` variant such as `CompletableFuture<T>`.

| Return type of @Async method | What does the caller receive? | Track completion/errors from the caller? | When appropriate |
| --- | --- | --- | --- |
| `void` | No Future/result handle | **No** via return value; requires logging, handler, or external state | Best-effort, caller needs no direct feedback |
| `Future<T>` | Future representing the asynchronous result | `get()`, `isDone()`, `cancel()` | Need to know completion/receive result, Future API is acceptable |
| `CompletableFuture<T>` | Future supporting callbacks and composition | `whenComplete`, `exceptionally`, `thenApply`… | Need to chain steps, handle errors asynchronously |
| `CompletableFuture<Void>` | No business data, but provides a completion handle | **Yes**, via completion/exception of the Future | No payload needed, yet success/failure still needs to be known |

A common point of confusion is that `CompletableFuture<Void>` **is not the same as** `void`. Neither returns business data, but the former returns an **object representing status** to the caller.

Spring integration example:

~~~java
@Async("backgroundExecutor")
public CompletableFuture<Void> warmWithCompletion(String key) {
    // Perform work in the worker.
    System.out.println("Warming: " + key);
    return CompletableFuture.completedFuture(null);
}
~~~

This is an **illustrative method**, not a standalone `javac` program; it must be placed in a Spring-managed bean with async configuration. With this approach, the Spring proxy returns a `CompletableFuture<Void>` for the caller to track. Inside the target method, `completedFuture(null)` is an interim result after the method's work has executed; the Spring proxy is what provides the asynchronous future to the caller.

If the method fails, the caller can register:

~~~java
CompletableFuture<Void> result = worker.warmWithCompletion("catalog");
result.whenComplete((ignored, error) -> {
    if (error != null) {
        System.err.println("Background work failed: " + error);
    }
});
~~~

This is also an **illustrative caller snippet**, assuming `worker` is a bean injected by Spring. Because the requirement is to know completion/error, using `CompletableFuture<Void>` makes more sense than `void` even though no data is returned.

### 3.1. TaskExecutor.execute(...) and ExecutorService.submit(...) Are Not the Same

Foundational Java APIs:

~~~java
executor.execute(runnable);             // Returns no handle: void
Future<?> future = service.submit(task); // Returns a Future handle
~~~

These are **two illustrative calls**, requiring corresponding `executor` and `service` variables. `execute(Runnable)` returns `void` per the `Executor` contract. `ExecutorService`'s `submit(...)` returns a `Future`. In Spring, `TaskExecutor` focuses on `execute(...)`, while some extensions such as `AsyncTaskExecutor` support `submit` so the caller receives a Future.

With `execute`, task exceptions are observed via the executor/caller thread mechanism, rather than automatically being wrapped into a returned Future. With `submit`, exceptions are typically held inside the `Future` and exposed when the caller calls `get()`. Do not assume the two APIs have the same error behavior just because both run on a thread pool.

## 4. Timeline: void Does Not Mean Work Is Done

~~~text
HTTP thread                  Spring proxy / executor           Worker thread
    |                                  |                             |
    |-- cacheService.warm("A") ------->|                             |
    |                                  |-- accept task / queue ------|
    |<-- void call returns ------------|                             |
    |                                  |       wait for worker       |
    |-- return HTTP response           |                             |
    |                                  |-- dispatch task ----------->|
    |                                  |                         start warm
    |                                  |                         execute
    |                                  |                         done or error
~~~

The scenario above assumes the pool has a queue and workers are busy. The task can also start **before the `void` call on the caller returns** if the executor has an idle worker. Additionally, with `SyncTaskExecutor`, the task runs synchronously; with a `CallerRunsPolicy` under overload, the task may run on the caller.

Therefore, the accurate statement is: **`@Async void` allows the caller not to wait and not to directly receive the completion result if submission is handled asynchronously**; there is no guarantee that "the task definitely starts after the caller returns."

The milestones to measure independently are `t_submit`, `t_start`, and `t_finish`. Time from submit to start may be spent in the queue. Even if an API returns fast while the queue waits many seconds, that still affects processing timeliness, even though the caller receives no Future.

## 5. Standalone Java 17: execute Returns void, Worker Still Runs Afterward

This example uses standard Java to observe the difference without needing Spring. Two latches allow confirming that the task has started and holding it from finishing before the caller checks.

Create the file **`VoidExecutorDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class VoidExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    System.out.println("3. Background task finished");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }
            System.out.println("1. execute() returned without a Future");
            System.out.println("2. Task finished? " + (finished.getCount() == 0));
            release.countDown();
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not finish");
            }
            System.out.println("4. Main observed completion with CountDownLatch");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Run commands:

~~~bash
javac --release 17 VoidExecutorDemo.java
java VoidExecutorDemo
~~~

Stdout **verified** when compiled with `--release 17`:

~~~text
1. execute() returned without a Future
2. Task finished? false
3. Background task finished
4. Main observed completion with CountDownLatch
~~~

Explanation:

1. `execute(...)` returns no `Future`; the callback may be executing or waiting. The program calls `started.await(...)` to ensure the worker has started.
2. The worker waits on `release`; therefore, at the moment main prints the second line, the task has definitely **not finished yet**.
3. Main opens the latch; the worker prints its message and decrements `finished`.
4. Only through an intentionally added synchronization mechanism (`finished.await(...)`) can main verify the task has ended. **This is not a result returned by `execute(void)`.**

This example demonstrates a case where the caller intentionally **adds tracking** even though the `execute` API itself has no Future. If the caller does not need to know completion, it can skip waiting on a latch; however, in tests, latches help produce deterministic results. `shutdownNow()` is only to release the worker when the program ends, not a mechanism guaranteeing that all tasks in a real application have been processed successfully.

## 6. Spring Framework: @Async void Example with a Bounded Executor

The following files are **integration code** for Java 17+, Spring Framework 6.x (or a compatible Spring Boot application) with `spring-context`, annotation processing, and component scanning. They **do not compile with a single `javac` command missing Spring dependencies**. Each class resides in a file of the same name in package `example.concurrency`.

### 6.1. Configuration Enabling @Async and Selecting an Executor

File `AsyncConfiguration.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Bean("bestEffortExecutor")
    public ThreadPoolTaskExecutor bestEffortExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("best-effort-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, args) ->
                System.err.println("Async void failed in "
                        + method.getName() + ": "
                        + exception.getClass().getSimpleName());
    }
}
~~~

Explanation:

- `@EnableAsync` enables the interceptor mechanism for `@Async` in the Spring ApplicationContext.
- `@Bean("bestEffortExecutor")` gives an explicit name. `@Async("bestEffortExecutor")` selects this bean instead of relying on the default executor. Spring manages initialization/lifecycle of the executor bean.
- `core=2`, `max=4`, `queueCapacity=20` are illustrative numbers. Beyond core, the executor typically prioritizes enqueueing. A saturated pool can reject tasks; not every call will be accepted.
- `AbortPolicy` makes rejection errors explicit. In `ThreadPoolTaskExecutor`, the exception is exposed according to Spring's `TaskExecutor` contract, typically `TaskRejectedException`.
- `getAsyncUncaughtExceptionHandler()` registers a **handler for uncaught exceptions inside `@Async void` targets**. The example only prints the method name and exception type; production should use structured logging/metrics, severity classification, and sensitive-data limits.

`AsyncConfigurer` is processed early during bootstrap; the example avoids injecting complex beans into the handler. If the application needs a logger or alerting system, implement it consistently with Spring's lifecycle. There should only be an intentional global async configuration, avoiding multiple configurations competing to decide the handler.

### 6.2. Service That Does Not Need to Return a Direct Result

File `CacheWarmService.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class CacheWarmService {
    private final ConcurrentMap<String, Boolean> warmed =
            new ConcurrentHashMap<>();

    @Async("bestEffortExecutor")
    public void warm(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Cache key must not be blank");
        }
        // Simulate work to warm a regenerable cache.
        warmed.put(key, Boolean.TRUE);
    }

    public boolean isWarm(String key) {
        return Boolean.TRUE.equals(warmed.get(key));
    }
}
~~~

This is a simple example that compiles **in a Spring application with dependencies declared**, but it does not represent a multi-node cache system. The map resides only in the memory of **a single application instance**. Real business logic may call a repository or cache backend, use timeouts when I/O is involved, and follow the system's retry/overload policies.

When another bean calls `cacheWarmService.warm("catalog")` through the Spring proxy:

1. Spring submits the call to `bestEffortExecutor`.
2. The caller receives no `Future` because the signature is `void`.
3. A worker may execute immediately or have to wait in the queue.
4. When executed, `warm(...)` updates the map. The caller is not notified directly when it finishes.
5. If an invalid `key` causes the method to throw an exception **in the worker**, the exception is routed to `AsyncUncaughtExceptionHandler` rather than returning to the caller's stack after the task was successfully submitted.

The `isWarm(...)` method is only intended to illustrate a **separate status-checking channel**, not an automatic acknowledgment of the `void` method. In a real system, you must clearly distinguish between not-yet-accepted, queued, running, succeeded, and failed states if status is a business requirement.

### 6.3. Caller from Controller and the Meaning of HTTP 202

File `CacheWarmController.java` (requires Spring Web MVC):

~~~java
package example.concurrency;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/cache")
public class CacheWarmController {
    private final CacheWarmService cacheWarmService;

    public CacheWarmController(CacheWarmService cacheWarmService) {
        this.cacheWarmService = cacheWarmService;
    }

    @PostMapping("/warm/{key}")
    public ResponseEntity<Void> requestWarm(@PathVariable String key) {
        if (key.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        try {
            cacheWarmService.warm(key);
            return ResponseEntity.accepted().build();
        } catch (TaskRejectedException ex) {
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).build();
        }
    }
}
~~~

What matters is that **the controller calls another bean**; the call goes through the Spring proxy of `CacheWarmService`. `202 Accepted` here only describes that **the request has been successfully submitted to the in-memory executor mechanism**. It does not promise "the cache has been warmed" or "the work will definitely survive a restart."

Keep the boundaries of this example in mind:

- Catching `TaskRejectedException` in the caller handles errors **before/during task acceptance** caused by the executor having no remaining capacity. Depending on executor configuration/rejection policy, some mechanisms may run the task on the caller or drop it without throwing; you must choose the policy deliberately.
- If the worker accepts the task and later throws an exception, the HTTP response **already sent does not automatically turn into 500**. That case is observed by the handler or an independent status channel.
- Very fast completion of `warm(...)` may happen **before the controller returns 202**, but a `void` call provides no such guarantee.
- If business requirements dictate returning 202 only after the work is durably stored, the controller must write to a durable queue/job store first, and only then acknowledge per the API contract.

For a regenerable cache-warming problem, this best-effort implementation is reasonable for illustration. Do not use it as-is for payments, mandatory auditing, or tasks that must not be lost.

## 7. Where Do Errors in @Async void Go?

This is the most important technical difference between `void` and `Future` when designing a return contract.

### 7.1. Exceptions Inside the Worker Do Not Automatically Return to the Caller

Example:

~~~java
@Async("bestEffortExecutor")
public void sendBestEffort(String id) {
    throw new IllegalStateException("Simulated background failure");
}
~~~

This is an **illustrative method** placed in a Spring bean, not a complete standalone class. If called through a proxy and the executor accepts the task, the exception occurs **on the worker**. The caller has already moved on, so it cannot use `try/catch` around the call to catch that execution exception as a synchronous error.

With an `@Async` method returning a `Future`, execution exceptions can be represented through the Future for the caller to observe via `get()` or a callback. With `void`, Spring provides `AsyncUncaughtExceptionHandler`. If none is configured explicitly, Spring's default handler logs the exception; it does not turn the call into a Future.

### 7.2. Two Types of Errors Must Have Separate Handling Channels

| Error | Where does it happen? | How can the caller handle it? |
| --- | --- | --- |
| Invalid input data before submission | Caller thread, if validated at the boundary | Return 400 / validation error synchronously |
| Executor rejects task at submission time | Call through Spring proxy, before work is accepted | Catch `TaskRejectedException` if policy throws; return 503 / throttle |
| Business error inside `@Async void` method | Worker after accepting the task | Handler/log/metrics, retry or independent state; cannot change an already-sent response |
| JVM dies or instance is terminated after accepting task | Outside the method's normal exception path | Recover work from durable job store/queue if business requires |
| Task interrupted due to shutdown/cancellation | During execution/pool closing depending on config | Handle interruption and decide whether the task needs retry/recovery |

You must distinguish errors from tasks **already accepted** and errors **not accepted**. `AsyncUncaughtExceptionHandler` handles uncaught exceptions from `@Async void` methods; it is not a replacement system for all cases of pool rejection, crashes, or tasks that never ran.

### 7.3. The Handler Is Not an Automatic Retry Mechanism

The handler receives information about the exception, `Method`, and arguments. It can log, emit metric signals, or send alerts via a separate system. **It does not automatically re-run the method** and does not guarantee the work is processed successfully.

If implementing retries yourself, you must consider idempotency, attempt counts, backoff/jitter, timeouts, and the risk of causing retry storms when downstream fails. If the handler resubmits work to the same saturated executor, it can worsen overload.

Do not print raw arguments in logs/alerts by default: they may contain emails, tokens, personal data, or large payloads. In the example in section 6, the handler only logs the method name and exception type to keep the illustration concise.

## 8. Cases Where void Is Insufficient

### 8.1. Needing to Know Success/Failure Even Without a Payload

Use `CompletableFuture<Void>`. The caller can:

~~~java
CompletableFuture<Void> future = worker.warmWithCompletion("catalog");
future.whenComplete((unused, error) -> {
    if (error != null) {
        System.err.println("Warm failed: " + error);
    } else {
        System.out.println("Warm completed");
    }
});
~~~

This snippet assumes the `worker` method and bean from section 3. If calling `future.join()` or `get()` immediately, the caller blocks until completion. Blocking is unnecessary if you only want to attach a callback; that is an important benefit of a completion stage.

### 8.2. Needing to Cancel Work

`@Async void` does not return a handle for the caller to call `cancel(...)` on that exact invocation. If the contract requires cancellation, you can use `Future`/`CompletableFuture`, or a job id with a dedicated cancellation mechanism. Even with a Future, `cancel(true)` only requests interruption when the task and libraries support it; it does not automatically roll back side effects that already occurred.

### 8.3. Needing Continuous Status or Later Results

You do not necessarily have to wait within the HTTP request, but you can return a job id and let clients call a status-checking endpoint. In that case, the system needs to store at least `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` (and canceled status if applicable), along with timestamps, errors, and retention rules. Job id and job store are a business contract independent of the worker method's return type.

### 8.4. Work That Must Not Be Lost

An in-memory executor only accepts tasks into the process's workers/queue. If the JVM crashes or the app is killed before the task finishes, a `void` call has no automatic recovery mechanism. For mandatory work, consider a durable queue, transactional outbox, job store, retry/idempotency, and an explicit recovery mechanism.

You should not call `void` "unsafe" by the data type itself: a `void` worker can still read from a durable queue orchestrated by another component. The issue is that **the caller has no return handle**, and reliability depends on the entire architecture.

## 9. Pitfalls with Proxy, Transactions, and Thread Context

### 9.1. Self-Invocation Prevents @Async from Being Applied

In the default proxy configuration:

~~~java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Internal call, usually DOES NOT go through the @Async proxy.
    }

    @Async("bestEffortExecutor")
    public void inner() {
        System.out.println("Inside worker?");
    }
}
~~~

This is an **illustrative Spring snippet**, with corresponding imports. `outer()` calling `inner()` directly on the same instance typically bypasses the proxy. `inner()` may run synchronously on the caller despite being annotated with `@Async`. The standard approach is to extract the async method into another bean and call it through the Spring-managed bean, like `CacheWarmController → CacheWarmService` above.

Do not put `@Async` on lifecycle callbacks like `@PostConstruct` expecting Spring to automatically run them in the background in the usual way. If you need to trigger work after startup, arrange a separate orchestrating bean and consider appropriate lifecycle/readiness.

### 9.2. Thread Context Is Not Automatically Transferred to the Worker

Some information in a Spring application is bound to the current thread, such as transaction context, request context, MDC, or security context. When `@Async` switches to another worker, **do not assume by default** that they are automatically transferred completely and safely.

For example, the caller being inside a transaction does not mean the caller's thread-bound transaction automatically continues in the worker. If the async task needs its own transaction, design transaction boundaries **inside the async processing flow itself** using appropriate Spring configuration. For trace/MDC, you can use a task decorator or a library-defined context propagation mechanism.

### 9.3. The void Type Does Not Guarantee Execution Off the Caller

`TaskExecutor` has different implementations. `SyncTaskExecutor` runs synchronously on the calling thread. `ThreadPoolExecutor`'s `CallerRunsPolicy` can run the task on the caller when the pool is saturated and not shut down, instead of rejecting.

Therefore, "using `void` to reduce latency" is only true if the execution path is genuinely configured appropriately and does not block the caller. Measure request latency, submit time, active workers, and queue wait to verify.

## 10. Monitoring void Work in Production Operations

Even though the caller does not need to receive a result, the system should still know whether tasks have actually been processed. A basic observability set:

| Metric/info | Where to measure | Meaning |
| --- | --- | --- |
| Number of submit calls | Caller boundary | How many background processing requests occurred |
| Number of rejected submits | Proxy/executor boundary | Detect overload or shutdown |
| Queue wait time | From acceptance to worker start | Measure delay before actual processing |
| Active tasks, queue depth, pool size | Executor | Concurrency limits and backlog |
| Execution duration | Worker start → finish | Detect slow I/O or contention |
| Succeeded/failed task counts | Inside method, handler, or job system | Distinguish "accepted" from "finished processing" |
| Correlation/job id | Caller and worker | Correlate logs/traces of a task |
| Shutdown/timeout/retry | Lifecycle and downstream | Detect truncation or repetition |

With `ThreadPoolTaskExecutor`, you can monitor `getActiveCount()`, `getPoolSize()`, `getQueueSize()` (in supported Spring versions) and corresponding instrumented metrics. Looking only at the number of submitted tasks cannot tell you how many tasks completed.

When naming metrics, choose clear names: `submitted_total`, `accepted_total`, `rejected_total`, `started_total`, `completed_total`, `failed_total`. These are **suggested metric names for applications**, not a list of default metric APIs automatically exported by Spring.

### 10.1. Shutdown and Redeployment

When the application context closes, the executor has a shutdown lifecycle according to the Spring version's configuration. Task wait time, behavior for accepting new tasks, and task interruption must be chosen to match requirements. Never conclude "once submitted, the task will definitely finish before pod restart."

If the task is only a repeatable cache warm, losing one run during shutdown may be acceptable. If the task is mandatory, use a more durable mechanism rather than simply extending the pool shutdown wait time.

## 11. Testing @Async void Properly

Because the caller has no Future, tests checking completion need a **deliberate synchronization signal or spy/collaborator**:

1. Use a real test ApplicationContext with `@EnableAsync` and the chosen executor; invoke the method through the bean proxy, not by calling `new Service()`.
2. Inject a test collaborator (or latch) to confirm the target method ran; use a finite timeout when waiting so tests do not hang indefinitely.
3. Test both the success branch and exception branch of the `void` method; for exceptions, verify the handler is invoked or the error metric increments. Do not expect the caller's `try/catch` to see errors thrown on the worker.
4. Simulate an executor refusing additional tasks to test rejection policies at the caller. You do not need to generate arbitrarily large load; a small bounded executor with a latch suffices to reproduce it.
5. Test shutdown/restart if the system requires zero task loss; unit tests of a service do not prove queue durability.

If a test uses `SyncTaskExecutor`, code may run immediately on the test thread. That is useful for checking simple logic, but **it does not verify real async queue behavior and timing**. Have a separate integration test for the path through the proxy and executor.

## 12. Misconceptions to Avoid

**"The method returns void so it runs in the background."** False. `void` is only a return type; proper executor configuration and interception are required if you want asynchronous execution.

**"No Future means the task definitely cannot fail."** False. Exceptions inside the worker still occur; with `@Async void` you need a handler/log/metrics or a dedicated business mechanism.

**"Catching `Exception` in the caller around an `@Async void` method catches all errors."** False. The caller usually only catches errors occurring at the submission step, such as rejection; execution errors after task acceptance follow the async handling path.

**"Returning HTTP 202 means the task processed successfully."** False. You must distinguish accepted from completed, and in-memory submit from durable acceptance.

**"If there is no data to return, you must use void."** Not mandatory. `CompletableFuture<Void>` is better if the caller needs completion info, exceptions, or a mechanism to compose further tasks.

**"@Async in the same bean still runs asynchronously when calling this.method()."** False in default proxy mode; internal calls do not go through the proxy.

**"void fire-and-forget does not need logging or retries."** False. Error-handling requirements depend on the business logic; not receiving a direct result still requires observability and overload policies.

**"You can cancel an `@Async void` invocation using a Future."** No Future is returned from a `void` method; you need to design a separate handle or switch to Future if the contract requires cancellation.

**"Every task submitted to an executor runs immediately."** False. Queue, core/max, CPU/I/O, and downstream resources determine when execution actually starts.

## 13. Decision Scenarios Based on Business Requirements

A product has a report generation feature and wants to invoke auxiliary tasks:

- **Warming a regenerable report data cache:** the caller does not need the result immediately; failures can be recorded as metrics and retried on the next pass. `@Async void` is a reasonable option if the executor is controlled and task-loss risk is understood.
- **Generating a report file for the user to download:** the caller needs to know the report id, status, and download link upon completion. `@Async void` alone is insufficient for the contract. You can use a job id/status store, or `CompletableFuture<Report>` for an in-process workflow.
- **Sending a mandatory transaction receipt:** the caller may not need to wait for the email to finish sending, but the system must know which receipts have not been sent and must retry. A durable queue/outbox with state and idempotency is more suitable than a pure in-memory `@Async void` call.
- **Updating auxiliary counters where minor discrepancy is acceptable:** `void` can suffice if failure metrics are tracked and task submission rate does not exceed pool capacity.

Decision rule:

~~~text
Does the caller need the business result immediately?
    |
    +-- Yes --> Future<T> / CompletableFuture<T> or appropriate synchronous processing
    |
    +-- No ---> Need to know completion/error/cancel via a return handle?
                     |
                     +-- Yes --> CompletableFuture<Void> / job id + status
                     |
                     +-- No ---> Is best-effort/repeatable work acceptable?
                                      |
                                      +-- Yes --> @Async void + handler + metrics
                                      |
                                      +-- No ---> Design durable acceptance,
                                                  retry/idempotency, and state
~~~

This is a contract-selection diagram, not a rule of a single framework. The same business domain may choose different models depending on SLA, criticality, and how the system already stores tasks.

## 14. Self-Check Questions

**Question 1.** Is a Java method returning `void` inherently asynchronous?

**Answer:** No. The `void` type does not create a thread and does not decouple the call. In Spring, `@Async` and a configured executor are required, and the caller must go through the interceptor/proxy.

**Question 2.** The caller invokes `@Async void warm()` and the call returns. Do we know if warming succeeded?

**Answer:** No. We only know the call has returned; if the task was submitted, it may be queued, running, or finished. To know success, another observation channel or a Future is needed.

**Question 3.** Why is `CompletableFuture<Void>` sometimes better than `void` even though it returns no payload?

**Answer:** A Future provides a handle to track completion, errors, attach callbacks, and request cancellation when supported.

**Question 4.** Are exceptions thrown from an `@Async void` target propagated to the controller via `try/catch`?

**Answer:** Not via the synchronous path after the task has been successfully submitted. Spring uses `AsyncUncaughtExceptionHandler` for uncaught exceptions from `void` methods; rejection at the submission step is a separate matter.

**Question 5.** If the pool is saturated, does an `@Async void` method always return normally?

**Answer:** No. With `AbortPolicy`, submission can fail and Spring may throw `TaskRejectedException` at the caller.

**Question 6.** Why shouldn't pure in-memory `@Async void` be used to guarantee payment processing?

**Answer:** Because there is no direct result contract or durability guarantee; a crash can lose tasks. State, idempotency, retries, and appropriate durable acceptance are needed.

**Question 7.** In the Java 17 example, how does main know the task finished even though `execute` returns `void`?

**Answer:** Through the separately added `CountDownLatch finished` and `await(...)`. That is not a return value of `execute`.

**Question 8.** Should we measure successful tasks by counting `@Async void` calls at the caller?

**Answer:** No. You must separate submitted, rejected, started, completed, and failed; the caller only measures part of the path.

## 15. References

- Spring Framework — Task Execution and Scheduling, `@Async` and exception handling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 API — `@Async` and supported return types: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework 6.2 API — `@EnableAsync`, `AsyncConfigurer`, `void` error handling and proxies: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework 6.2 API — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Java SE 17 — `Executor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 17 — `ExecutorService` and `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
