# Submission Exceptions Differ from Execution Exceptions

In Spring Framework, an `@Async` call or `TaskExecutor.execute(...)` can fail at **two points with very different meanings**:

1. **During submission (submission/admission):** the executor cannot or refuses to accept the work, for example because the pool has shut down or both workers and queue are saturated. The error occurs on the submission call path and can usually be detected immediately by the caller.
2. **During execution (execution):** the executor has accepted the work and a worker starts executing it, but the business logic throws an exception. How the error is propagated depends on the API: `Future`, `CompletableFuture`, `@Async void`, or `execute(Runnable)` directly.

Distinguishing between these two error categories determines where to place `try/catch`, which HTTP status to return, how to record metrics, how to configure exception handlers, and how to choose a retry strategy. **Just because “there is an executor” does not mean exceptions will be sent back to the caller thread**, nor is every error appearing near `execute(...)` a business error.

This lesson belongs to the **Exception Handling** group in the **Spring Framework - concurrency** module. The integration code snippets use Spring Framework 6.x and Java 17+; the standalone Java programs below can be compiled and run immediately with JDK 17.

## 1. Two distinct phases: task acceptance and execution

A typical lifecycle:

~~~text
HTTP / service caller                TaskExecutor / queue                 Worker
          |                                   |                               |
          |---- execute / submit(task) ------>|                               |
          |                                   |--- try to accept task ------->|
          |                                   |                               |
          |       +---------------------------+                               |
          |       | REJECT: out of capacity, shutdown, policy                 |
          |<------X  submission exception, task was not accepted              |
          |                                                                   |
          |<------ accepted / Future ---------|                               |
          |                                   |-- wait for worker ----------->|
          |                                   |                           task.run()
          |                                   |                              |
          |                                   |                     +--------+--------+
          |                                   |                     |                 |
          |                                   |                   success           throw
          |                                   |                     |                 |
          |                                   |                 completed       execution failure
          |                                   |                                       |
          |                                   |                         Future / handler / log
~~~

The diagram illustrates a scenario with an asynchronous thread pool and an exception-throwing rejection policy; synchronous implementations and `CallerRunsPolicy` may have a different order, which is analyzed in a later section.

| Characteristic | Submission exception | Execution exception |
| --- | --- | --- |
| Timing | Before the executor accepts the task or during the submit call itself | After the task has been accepted and execution logic has started |
| Typical issues | Pool overloaded, queue full, executor shut down, no remaining capacity to accept | Invalid data, DB/HTTP errors, parse failures, business rules, NPE, I/O timeout |
| Common in Java | `RejectedExecutionException` from `execute`/`submit` | Exception thrown inside `Runnable.run()` or `Callable.call()` |
| Common in Spring | `TaskRejectedException` from `TaskExecutor` | Exception inside an `@Async` target method |
| How does the caller see it? | Usually thrown synchronously from the submit call when using an exception-throwing rejection policy | Depends on contract: `Future.get()`/`join()`, `AsyncUncaughtExceptionHandler`, or worker uncaught handler |
| Is the work guaranteed to have run? | **No** if rejected before acceptance | **Execution started** (but not necessarily completed successfully) |
| How to handle | Load shedding, appropriate 503/429, backpressure, pool/queue sizing, shutdown checks | Logging, classifying business errors, bounded retries, persisting failure state, and observing downstream |

Note that “exception at the submission call” and “exception of the task itself” are **two causal concepts**. The moment the caller observes the error may occur later than the original failure: for example, the exception may have been thrown in a worker long before, yet the caller only sees `ExecutionException` when calling `Future.get()`.

## 2. Submission failure: the task is not accepted

### 2.1. Why does an executor reject?

With `ThreadPoolExecutor`, and through it Spring's `ThreadPoolTaskExecutor`, the basic admission sequence is:

1. If the number of workers is below `corePoolSize`, try creating a new worker.
2. Once core size is reached, try placing the task into the queue.
3. If the queue cannot accept it, try increasing the number of workers up to `maxPoolSize`.
4. When there is no remaining capacity to accept, apply `RejectedExecutionHandler`.

Beyond saturation, **an executor that has already shut down can also reject new tasks**, even when CPU is idle or the queue is not full. Not seeing a full queue is not enough to rule out rejection.

Example with `corePoolSize=1`, `maxPoolSize=1`, `queueCapacity=1`:

~~~text
Task A: worker #1 is running and blocked
Task B: accepted and sits in the single queue slot
Task C: no free worker, queue is full
        -> AbortPolicy -> rejected on submit
~~~

When using Java's `ThreadPoolExecutor.AbortPolicy`, the `execute(C)` call throws `RejectedExecutionException`. In Spring's `ThreadPoolTaskExecutor`, the `TaskExecutor` contract typically exposes the corresponding case as `TaskRejectedException`, a subtype of `RejectedExecutionException`.

### 2.2. Catching errors at the submission boundary

Illustrative Java snippet:

~~~java
try {
    executor.execute(task);
    System.out.println("Submission accepted");
} catch (RejectedExecutionException ex) {
    System.err.println("Executor did not accept the task");
}
~~~

This is an **abbreviated snippet**, assuming `executor` and `task` have already been declared. In Spring with a `ThreadPoolTaskExecutor` bean, `TaskRejectedException` is typically caught at the submission boundary to decide whether to return an error, shed load, or persist the work to a durable queue if the business requires it.

Important: an `execute(...)` call returning normally only indicates that the task was handled according to the executor's **policy**, not that the task will run successfully. A policy may run the task on the caller or silently discard the task. Therefore, “no exception on submission” is **not** confirmation that the task was durably stored or completed.

### 2.3. Not every policy throws an exception

| `ThreadPoolExecutor` policy | When unable to accept more | Consequence for the caller |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Caller usually detects immediately; easy to distinguish overload |
| `CallerRunsPolicy` | If the executor has not shut down, the caller **runs** `Runnable` itself | The submit call may block and task exceptions may occur on the caller |
| `DiscardPolicy` | Drops the task, usually without throwing from the policy | No exception does not mean it was processed |
| `DiscardOldestPolicy` | Drops the task at the head of the queue and retries accepting the new task | May lose another task and break ordering/delivery expectations |

All of these policies carry business risks; choose based on load-handling requirements, tolerance for losing work, and how results are recorded. For example, a payment request should not use `DiscardPolicy` and rely solely on the submit method returning.

### 2.4. Exceptions coming from the caller are not necessarily rejection

If the caller parses arguments itself before submitting and throws `IllegalArgumentException`, that error belongs to **validation at the caller boundary**, not executor rejection. If an executor bean is missing or proxy configuration is wrong, the call may fail before the admission step; do not lump every synchronous exception into `TaskRejectedException`.

To classify accurately, measure and log the **cause, exception type, executor bean, and failure phase**, rather than merely logging “async failed”.

## 3. Execution failure: the task ran and then threw an error

After the executor accepts the task, a worker executes the logic. For example:

~~~java
Runnable task = () -> {
    throw new IllegalStateException("Business processing failed");
};
~~~

This is an illustrative `Runnable`. The error here is an **execution error inside the task**. When using a thread pool, it is typically not thrown back through the stack of the `execute(task)` method that already returned earlier.

What the caller observes depends on the API:

- **`Executor.execute(Runnable)` directly:** an uncaught exception in `run()` typically goes through the worker thread's uncaught exception mechanism; it does not produce a result Future for the caller. With `ThreadPoolExecutor`, a worker encountering a runtime error may terminate abruptly and the pool manages creating a replacement worker as needed.
- **`ExecutorService.submit(Runnable/Callable)`:** the task is typically wrapped in a `FutureTask`; exceptions in the worker are captured as the Future's failed state. A caller calling `get()` receives `ExecutionException`, and can inspect `getCause()` to see the root cause.
- **`CompletableFuture`:** when a task completes exceptionally, `whenComplete`/`handle`/`exceptionally` can be used to handle it. `join()` typically exposes the error via `CompletionException`; `get()` typically via `ExecutionException`.
- **Spring `@Async` returning `void`:** there is no returned Future, so Spring uses `AsyncUncaughtExceptionHandler` for uncaught exceptions from the target method.
- **Spring `@Async` returning `Future`/`CompletableFuture<T>`:** execution exceptions are propagated through the Future for the caller to observe; `AsyncUncaughtExceptionHandler` is not the primary channel for these cases.

**Do not equate “exception in the worker” with “exception already handled by the caller”**. If nobody calls `Future.get()`, attaches a completion callback, or instruments the task, a `submit` task failure may not be observed in time.

## 4. Java 17 — proving pre-execution rejection vs. worker-side error

The program below creates a verifiable scenario **without relying on `Thread.sleep`**. The pool has only one worker and a queue capacity of one task:

- Task A runs and holds the worker using a latch.
- Task B is submitted successfully into the queue, but when it runs it will throw a business error.
- Task C is rejected **right at the submission call** because both the worker and the queue are busy.
- After releasing the latch, B runs and B's Future completes exceptionally.

Create the file `SubmitVsRunErrorDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class SubmitVsRunErrorDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First worker did not start");
            }

            Future<?> second = pool.submit(() -> {
                throw new IllegalStateException("business failure");
            });
            System.out.println("1. Second task accepted");

            try {
                pool.execute(() -> System.out.println("never run"));
                System.out.println("unexpected acceptance");
            } catch (RejectedExecutionException ex) {
                System.out.println("2. Third task rejected during submission");
            }

            release.countDown();
            try {
                second.get(5, TimeUnit.SECONDS);
                System.out.println("unexpected success");
            } catch (ExecutionException ex) {
                System.out.println("3. Second task failed while running: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("4. Second task done=" + second.isDone());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac --release 17 SubmitVsRunErrorDemo.java
java SubmitVsRunErrorDemo
~~~

Stdout verified with JDK compiled with `--release 17`:

~~~text
1. Second task accepted
2. Third task rejected during submission
3. Second task failed while running: IllegalStateException
4. Second task done=true
~~~

**Explanation of why the result is deterministic:**

1. `started.await(...)` waits until A has actually started. A will not leave the worker before `release.countDown()`.
2. When B is `submit`ted, the queue has exactly one slot left and is filled by B; the Future is returned before B can run.
3. C arrives while A still holds the worker and B still occupies the queue; `AbortPolicy` immediately throws `RejectedExecutionException`. C **does not run**, has no Future, and produces no business exception from C.
4. `release.countDown()` lets A exit; the worker picks up B. B throws `IllegalStateException` inside the worker, which is captured in the Future.
5. `second.get(...)` throws `ExecutionException` on the caller **when reading the result**; `getCause()` is the original `IllegalStateException`. `isDone()==true` does not mean B succeeded; a failed state is also considered done.

This example does not pretend to measure specific timings. For production code, also account for timeouts, admission control, logging, and controlled shutdown.

## 5. Java 17 — why direct execute differs from submit when a task throws

A subtle detail: **`execute(...)` does not necessarily create a `FutureTask`**, whereas `submit(...)` typically wraps the task to store the result and exception.

With `ThreadPoolExecutor.execute(rawRunnable)`, an uncaught exception may go to the worker's `Thread.UncaughtExceptionHandler`. With `ExecutorService.submit(rawRunnable)`, `FutureTask` records the error and `Future.get()` provides the path for the caller to read it; the worker's uncaught handler is usually **not invoked because `FutureTask` caught the exception**.

The following program demonstrates the direct `execute` side, without Spring. Create the file `ExecuteUncaughtDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class ExecuteUncaughtDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch handled = new CountDownLatch(1);
        ThreadFactory factory = task -> {
            Thread worker = new Thread(task, "worker-example");
            worker.setUncaughtExceptionHandler((thread, error) -> {
                System.out.println("1. Uncaught on " + thread.getName()
                        + ": " + error.getClass().getSimpleName());
                handled.countDown();
            });
            return worker;
        };
        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("worker crash");
            });
            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler was not called");
            }
            System.out.println("2. Main observed uncaught handler");
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 ExecuteUncaughtDemo.java
java ExecuteUncaughtDemo
~~~

Verified stdout:

~~~text
1. Uncaught on worker-example: IllegalStateException
2. Main observed uncaught handler
~~~

A limitation to understand: this is the behavior of **Java `ExecutorService` with `execute(rawRunnable)`**. Spring `@Async` has its own interceptor and exception-handling mechanism, so do not infer that every `@Async void` error definitely reaches the worker's `Thread.UncaughtExceptionHandler`.

Counting errors solely via an uncaught handler is also insufficient if the system uses `submit`, `CompletableFuture`, or exception-catching wrappers. Observation of results must match the API actually used.

## 6. Spring Framework: one executor, two clear error channels

This section contains **integration code in Spring Framework 6.x / Java 17+**; it requires Spring Context, Spring AOP, component scanning, and `@EnableAsync`. Each `public class` resides in a file of the same name in package `example.concurrency`. The following snippets **will not run with standalone `javac` without Spring dependencies**.

### 6.1. Configuring ThreadPoolTaskExecutor and the handler for @Async void

File `AsyncErrorConfiguration.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {

    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, args) ->
                System.err.println("Async void execution failed: "
                        + method.getName() + " / "
                        + exception.getClass().getSimpleName());
    }
}
~~~

Meaning:

- `jobExecutor` is the single executor bean selected by the example via `@Async("jobExecutor")`. `@EnableAsync` activates how Spring intercepts calls through a proxy.
- `core=2`, `max=4`, `queueCapacity=16` are demo values only, not general production recommendations.
- `AbortPolicy` ensures a saturated pool produces an explicit rejection signal at the submit call; with Spring's `ThreadPoolTaskExecutor`, you typically see `TaskRejectedException`.
- `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` is used by Spring for unhandled exceptions from **`@Async void` target methods**. The example only prints method name and error type; in production, use structured logging, metrics, correlation id, and avoid exposing sensitive arguments.

Spring automatically manages the lifecycle/initialization of the executor bean. You do not need to call `initialize()` inside the factory method if the bean is created by `ApplicationContext` through the standard mechanism.

### 6.2. A worker with two types of async methods

File `JobWorker.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobWorker {

    @Async("jobExecutor")
    public CompletableFuture<String> generate(String jobId) {
        if (jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is blank");
        }
        if (jobId.equals("fail")) {
            throw new IllegalStateException("generate failed");
        }
        return CompletableFuture.completedFuture("generated:" + jobId);
    }

    @Async("jobExecutor")
    public void notifyBestEffort(String id) {
        if (id.equals("fail")) {
            throw new IllegalStateException("notification failed");
        }
        System.out.println("Notified: " + id);
    }
}
~~~

With `@Async("jobExecutor")` functioning properly:

- Calling `generate("ok")`: the caller receives `CompletableFuture<String>`; the task may wait in the queue before running. If successful, the Future completes with `"generated:ok"`.
- Calling `generate("fail")`: if submission succeeds, `IllegalStateException` occurs **on the worker**. The caller's Future completes exceptionally; the caller observes it via `whenComplete(...)`, `join()`, or `get()`.
- Calling `notifyBestEffort("fail")`: if submission succeeds, the error occurs inside the `@Async void` target method, and since there is no returned Future, Spring sends the uncaught error to `AsyncUncaughtExceptionHandler`.
- For **any** method, if the executor rejects right during the submit step, the caller may receive `TaskRejectedException` **before any async result exists**; the handler for `void` execution errors does not replace rejection handling.

The example uses `String.isBlank()` (Java 11+), so it is compatible with Java 17. This is illustrative logic; if parameters need validation **before submission**, validate at the caller controller/service boundary to return a synchronous 4xx error instead of pushing invalid data errors onto a worker.

### 6.3. Caller catches submission errors, Future receives execution errors

Snippet in another bean with `JobWorker worker` injected:

~~~java
try {
    CompletableFuture<String> future = worker.generate("fail");

    future.whenComplete((value, error) -> {
        if (error != null) {
            System.err.println("Execution failed: " + error);
        } else {
            System.out.println("Success: " + value);
        }
    });
} catch (org.springframework.core.task.TaskRejectedException ex) {
    System.err.println("Submission rejected: executor is not accepting work");
}
~~~

This is **illustrative caller code** with no fixed stdout because execution depends on the executor and load. The two observation branches are **not the same**:

- `catch (TaskRejectedException)` catches the situation where **work could not be submitted** under an exception-throwing rejection policy.
- `whenComplete((value, error) -> ...)` observes the **execution outcome** of an accepted task, which may have already started or still be queued when the caller registers the callback.

With `CompletableFuture`, `join()` typically throws `CompletionException` when the task fails, while `get()` throws `ExecutionException` (or exceptions related to cancellation/interruption). Both can wrap the real business exception as their cause; do not rely on the outer exception message string to classify errors. If the caller calls `join()` immediately after submitting, it will block waiting for the task and is no longer fully non-blocking.

### 6.4. How does a caller of @Async void handle both error sources?

Snippet in another bean:

~~~java
try {
    worker.notifyBestEffort("fail");
    // Returning normally only means the proxy call went through
    // the submit path under the current executor policy.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    System.err.println("Submission rejected");
}
~~~

If the task is accepted and then throws `IllegalStateException` in the worker, the `catch` above does not catch that error; the handler in `AsyncErrorConfiguration` is the channel for handling `@Async void` execution errors. If the task is rejected, that handler has no target exception to process because the method never ran.

With `void`, the caller has no handle to know whether the task has completed. If acknowledgement of success/failure is needed, use `CompletableFuture<Void>` or a job id/status mechanism instead of simply adding `@Async` to a `void` method.

## 7. Comparison table of exception paths by API

| API / contract | Task not accepted error | Target method execution error | Who typically sees it? |
| --- | --- | --- | --- |
| Java `ThreadPoolExecutor.execute(Runnable)` + AbortPolicy | `RejectedExecutionException` at `execute` | Uncaught on the worker if `Runnable` does not catch it | Caller for rejection; worker uncaught handler/log for execution error |
| Java `ExecutorService.submit(Callable)` | `RejectedExecutionException` at `submit` | Future completes exceptionally; `get()` throws `ExecutionException` | Caller when calling `get()`; metrics/callback if instrumented |
| Java `CompletableFuture.runAsync(..., executor)` | May throw `RejectedExecutionException` when the request is not accepted | `CompletableFuture` completes exceptionally | Caller on submit; callback/`join()` for execution error |
| Spring `TaskExecutor.execute(Runnable)` + AbortPolicy | `TaskRejectedException` | Depends on executor/wrapper type and uncaught handler | Caller for rejection; worker/instrumentation for execution error |
| Spring `@Async void` | `TaskRejectedException` at proxy submit | `AsyncUncaughtExceptionHandler` | Caller for submission error; handler for execution error |
| Spring `@Async CompletableFuture<T>` | `TaskRejectedException` at proxy submit | Future completes exceptionally | Caller for submission error; Future callback/`get()`/`join()` for execution error |

The table uses **an asynchronous executor with `AbortPolicy` or equivalent** as the baseline for comparison. Adjust interpretation when using `CallerRunsPolicy`, `DiscardPolicy`, `SyncTaskExecutor`, or custom wrappers. Do not turn this table into a conclusion that task exceptions **never** throw on the caller in any implementation.

## 8. Cases where exceptions cross phase boundaries

### 8.1. CallerRunsPolicy can run the target right on the caller

When the pool is overloaded and the policy is `CallerRunsPolicy`, an `execute(rawRunnable)` call may directly invoke `run()` on the caller. If `run()` throws an uncaught exception, that exception may appear directly **inside the `execute(...)` call**, even though its cause belongs to **execution logic**, not the executor rejecting via `AbortPolicy`.

Conversely, if a task submitted with `submit(...)` is wrapped in a `FutureTask`, the error may still be stored in the Future even when `CallerRunsPolicy` causes it to execute synchronously on the caller. **The wrapper type and policy matter more than reasoning “it threw early so it must be a rejection”.**

### 8.2. SyncTaskExecutor does not switch to another worker

Spring's `SyncTaskExecutor` runs `Runnable` on the calling thread. If the method throws an exception, the caller may see it immediately. This is not an exception “returned from a background thread”. When tests use a synchronous executor while production uses a thread pool, test results regarding timing and exception propagation can differ. Always have integration tests verifying the real executor.

### 8.3. Self-invocation bypasses the @Async proxy

In default proxy mode, a bean method calling `this.otherAsyncMethod()` inside the same bean typically does not pass through the `@Async` interceptor. The method may run **synchronously** on the caller and throw an exception immediately, misleading learners into thinking worker errors automatically propagate back to the caller.

Verify `@EnableAsync`, Spring-managed beans, and that calls go through the proxy before concluding about error behavior. In practice, async methods are often separated into another bean to keep call paths clear.

### 8.4. Exceptions caught inside the worker

If a method catches an exception itself and returns normally, the Future may complete successfully or the handler may not be invoked, even though an internal business step failed. This is not “Spring losing exceptions”; it is the consequence of the code **swallowing errors**.

Only catch when there is a real handling strategy: returning a result representing the error, updating status, bounded retrying, or rethrowing to fail the Future/route through the handler. Do not use `catch (Exception ignored)` for mandatory work.

## 9. From technical exceptions to HTTP responses and SLAs

Suppose an endpoint submits a background report generation request:

| Scenario | Reasonable response at API boundary | Meaning of the response |
| --- | --- | --- |
| Invalid input before submission | `400 Bad Request` when appropriate | Invalid request; task not submitted |
| Executor saturated, refuses to accept task | `503 Service Unavailable` or `429 Too Many Requests` depending on contract | System did not accept the work; caller knows to throttle/retry |
| Task accepted into in-memory executor | May return `202 Accepted` per API contract | Submitted; **not yet** a guarantee of success or durability |
| Task runs and fails after HTTP response was sent | Cannot change status of the previous response | Need job status channel, completion event, metrics/logs/alerts |
| Work requiring durable persistence | Acknowledge based on successful persistence into job store/queue | Do not equate `ThreadPoolTaskExecutor.execute` with durable acceptance |

`503` and `429` are not mandatory Spring mappings for every `TaskRejectedException`; they are **API design decisions** depending on cause and throttling policy. Client retries require backoff/jitter and idempotency to avoid creating a new request storm.

With `@Async CompletableFuture<T>`, the caller can attach a callback or store a job id. If the endpoint has already returned `202`, subsequent errors should update status/raise alerts or notify via another channel; do not assume a failed completion will automatically turn the response into a 500.

## 10. Retries differ by phase

**When submission is rejected:**

- Check whether the cause is saturation or shutdown. If the node is shutting down, retrying the same node immediately may be futile.
- Choose backpressure, bounded queues, rate limiting, concurrency limits, and capacity balancing.
- If the business allows retries, set a retry budget, timeout/deadline, backoff, and jitter; avoid a `while(true) submit()` loop right on the request thread.
- For work that must not be lost, persist the task to a durable queue before or during an acknowledged admission protocol; an in-memory queue is not enough.

**When the task ran and then failed:**

- Distinguish transient errors (connections, downstream overload) from permanent errors (invalid input, unsatisfied business conditions).
- Retries must rely on **idempotency**: a previous run may have partially written data before throwing an exception. Do not assume re-running creates no duplicate side effects.
- Do not retry permanent validation errors indefinitely.
- If the Future completes exceptionally, decide job status, retry count, and how to report failure to the caller. With `@Async void`, the handler can raise alerts but has no built-in retry logic of its own.
- Maintain independent timeouts for HTTP/JDBC and end-to-end deadlines, not just for `Future.get(timeout)`.

In addition, cancellation/interruption is a separate branch. `Future.cancel(true)` can request interruption, but does not guarantee a running task stops immediately or rolls back completed operations. Being cancelled before execution is also not equivalent to a task running and failing with a business error.

## 11. Logging and metrics must separate submission errors from execution errors

When monitoring the system, record distinct event types instead of a vague “async failed” counter:

| Event | Recording point | Suggested details |
| --- | --- | --- |
| `submitted_total` | When caller starts submitting | Workload name/task type, correlation id |
| `accepted_total` | After executor accepts successfully under an acknowledged policy | Executor, queue size/limit, state at acceptance |
| `rejected_total` | When submission fails | Executor name, pool size, active count, queue depth, shutdown flag |
| `started_total` | Start of worker callback | Job id, wait duration since submission |
| `completed_total` | When task completes successfully | Runtime, workload |
| `execution_failed_total` | When task has started and failed | Exception category, downstream, retry count |
| `cancelled_total` | When cancelled | Whether task was queued or running, cancellation request outcome |

These are **suggested metric names**, not metrics Spring generates automatically with those exact names. Instrumentation must be placed properly: exceptions in a `FutureTask` may be stored inside the Future, so relying solely on `Thread.UncaughtExceptionHandler` or a `TaskDecorator` catching around `callback.run()` can **miss execution errors**.

With a `FutureTask`, the outer wrapper's `run()` may finish normally while the Future is already in a failed state. Depending on the executor type, you can observe `afterExecute(...)`, completion callbacks, or instrument at the business boundary itself. Avoid blocking workers with `get()` inside every callback if that can cause deadlock/starvation.

Do not log full payloads or exception arguments containing tokens/sensitive data. Use job id and trace id to correlate stages.

## 12. Testing both error types without relying on lucky timing

A good integration test has at least two **distinct** cases:

### 12.1. Case A: rejection right at the submission call

- Use an executor with core=max=1, queueCapacity=1, `AbortPolicy`.
- Use `CountDownLatch` to hold worker A.
- Submit B into the queue, then submit C.
- Assert C throws `TaskRejectedException` (in Spring) or `RejectedExecutionException` (Java) on the submit call.
- Assert task C's logic **was never invoked**.
- Release the latch and shut down the pool in `finally` so the test does not hang.

Do not just try submitting thousands of tasks with `Thread.sleep` and hope for rejection: such tests are flaky across CI machines.

### 12.2. Case B: error after the task has been accepted

- Submit work designed to throw `IllegalStateException` on the worker.
- With `Future`, assert `get()` throws `ExecutionException` with the expected cause; with `CompletableFuture`, assert the callback receives the error or the Future completes exceptionally.
- With `@Async void`, inject a testable `AsyncUncaughtExceptionHandler` and assert the handler is called with the expected method/exception.
- Assert that worker errors are not confused with `TaskRejectedException`.
- Invoke the method through the Spring proxy, without `new Service()` and without self-invocation, so the test genuinely goes through `@Async`.

### 12.3. Case C: special policies and lifecycle

Also test `CallerRunsPolicy`, `SyncTaskExecutor`, and shutdown when applicable. They can exhibit different behavior regarding threads and when exceptions surface. Verify tests do not rely on the assumption that “every task runs in the background”.

## 13. Common misconceptions

**“`try/catch` around `submit(...)` will catch every exception inside the task.”** No. It typically catches submission rejections/errors; task execution exceptions are stored in the Future and observed via `get()`/completion callbacks.

**“`Future.isDone() == true` means success.”** No. A Future may have completed via error or cancellation.

**“`@Async void` failing during execution will return to the controller.”** Not through the normal path once submitted asynchronously. Spring uses `AsyncUncaughtExceptionHandler`; the caller may have already returned a response.

**“Every exception appearing in `execute(...)` is a rejection.”** No. `CallerRunsPolicy` or a synchronous executor can run task logic right on the caller, and that logic may throw an exception.

**“`@Async CompletableFuture` means submission cannot fail.”** No. The executor can reject before a Future is returned to the caller.

**“Seeing no uncaught exception log means the submitted task did not fail.”** No. `submit` typically wraps exceptions in `FutureTask`; the worker's handler may not be invoked.

**“As long as the pool still has idle CPU, it will never reject.”** No. The pool may be shut down, workers may be blocked, the queue may be full, or max limits may be reached.

**“Once 202 has been returned, the task is guaranteed to complete.”** No. An in-memory queue can be lost on crash, the task can fail, and the already-sent response does not change.

**“Simply adding retry for every exception type is safe.”** No. Retrying permanent errors or non-idempotent side effects can duplicate actions and overload the system further.

## 14. Self-check exercises

**Question 1.** `ThreadPoolTaskExecutor` is saturated and configured with `AbortPolicy`; a controller calls an `@Async` method. Where does the exception occur and what should be done?

**Answer:** `TaskRejectedException` may be received right at the submission call (in the proxy). The controller needs to respond with overload/load-shedding/retry coordination, rather than waiting for a worker to process an unaccepted task.

**Question 2.** `ExecutorService.submit(...)` returns a `Future`; the task is accepted and then throws `IllegalArgumentException`. Will `try/catch` around the submit call reliably catch that error?

**Answer:** no. When calling `Future.get()`, the caller typically receives `ExecutionException` whose cause is `IllegalArgumentException`.

**Question 3.** When calling `CompletableFuture.join()` on a Future that completed exceptionally, what wrapper is typically encountered?

**Answer:** `CompletionException`, with a cause representing the execution failure; `get()` typically uses `ExecutionException`.

**Question 4.** An `@Async void` method was accepted but fails on the worker. Does the caller receive the error through the return value?

**Answer:** no. You need `AsyncUncaughtExceptionHandler`, logging/metrics, or a separate status channel.

**Question 5.** Why does `CallerRunsPolicy` make an “early/late” classification dangerous?

**Answer:** a raw `Runnable` may run on the caller inside the `execute(...)` call; a business exception will appear right at the submission method even though it is inherently an execution error.

**Question 6.** Why might `submit` not trigger the worker's uncaught exception handler when a task fails?

**Answer:** the task is wrapped by `FutureTask`, and the wrapper retains the exception for the caller to read via the Future.

**Question 7.** A receipt-creation task was submitted successfully, but the JVM crashed before a worker processed it. Is this an “execution exception” that `Future` is guaranteed to catch?

**Answer:** no. Crashes/loss-of-process lie outside the normal error-reporting path; a durable task admission/storage mechanism is needed.

**Question 8.** When monitoring quality, should there be a single `async_failed_total` counter or separate error types?

**Answer:** separate at least `rejected_total` (not accepted) and `execution_failed_total` (ran and failed); add completions, queue wait, and cancellations as needed.

## 15. Official references

- Spring Framework Reference 6.2 — Task Execution and Scheduling, `@Async`, Exception Management: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework API 6.2 — `ThreadPoolTaskExecutor` and `TaskRejectedException`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework API 6.2 — `@Async`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework API 6.2 — `@EnableAsync` / `AsyncConfigurer`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Oracle Java SE 17 — `ThreadPoolExecutor`, rejection policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `ExecutorService` / `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 17 — `ExecutionException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html
