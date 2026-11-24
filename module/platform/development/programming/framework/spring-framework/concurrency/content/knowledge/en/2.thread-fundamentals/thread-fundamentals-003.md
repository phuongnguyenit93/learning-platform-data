# Future and CompletableFuture: Representing Unfinished Work

In Java, a regular method call returns a result once the method has finished running. For a task running on another thread, when dispatching the work we may **not have the result yet**. **Future** and **CompletableFuture** provide an object representing a result that will become available in the future, including the possibility of failure or cancellation.

This lesson belongs to the **Thread Fundamentals** section of Spring Framework - Concurrency. The focus is on understanding task states, how to wait for or combine results, error handling, and executor selection. The final section connects Java knowledge to Spring **@Async**.

## 1. Distinguishing Task, Thread, and Result Object

- **Task**: the unit of work to be performed, such as a computation, service call, or data read.
- **Thread**: the execution resource for running tasks. An executor manages scheduling and running tasks on threads.
- **Future<T>**: a handle representing the result of type T for a submitted task. It is not the thread running the task itself.
- **CompletionStage<T>**: a contract describing processing steps that depend on a previous result.
- **CompletableFuture<T>**: implements both the Future and CompletionStage contracts, and also allows explicitly completing the result.

A future object may be pending, completed normally, completed exceptionally, or cancelled. **isDone()** reports completion *in any state*; it does not mean success. Future completion and the actual stopping of the background task also do not always coincide.

Mental flow:

~~~text
Caller                    Executor / worker
  | submit(task) ----------------> task runs
  | receives Future<T>       ... may not be done yet
  | does other work
  | get()/join() ---> waits if needed ---> receives T or error
~~~

**Asynchronous** describes how work is coordinated; it does not automatically mean "never blocks." Calling get() or join() on an unready result still blocks the calling thread.

## 2. Future: Receiving Results from ExecutorService

**ExecutorService.submit(Callable<T>)** accepts a value-returning function and immediately returns a **Future<T>**. Core operations:

| API | Meaning |
| --- | --- |
| submit(callable) | Submits a task and receives a Future representing the result. |
| isDone() | True if completed normally, failed, or cancelled. |
| get() | Waits until done; returns the result or throws an exception. |
| get(timeout, unit) | Waits at most a specified duration; may throw TimeoutException. |
| cancel(mayInterruptIfRunning) | Requests cancellation; for executor Futures, true may send an interrupt signal. |
| isCancelled() | True if the future was cancelled successfully. |

Standalone Java 17+ example, save as **FutureDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = executor.submit(() -> 6 * 7);

            System.out.println("Task submitted");
            System.out.println("Result: " + answer.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac FutureDemo.java
java FutureDemo
~~~

Standard output:

~~~text
Task submitted
Result: 42
~~~

Here the computation runs on the executor; get() is the synchronization point. If the task is not finished yet, the main thread waits. If you only submit a task and immediately call get(), you gain little ability to do other work while waiting.

**Three outcome branches of get():**

1. Task succeeds: returns T.
2. Task throws an exception: get() throws **ExecutionException**; the root cause is usually in **getCause()**.
3. Calling thread is interrupted: get() throws **InterruptedException**. In a handling layer that explicitly catches this exception, you normally must restore the interrupt flag via **Thread.currentThread().interrupt()** and then stop or return an appropriate error. If the limit in get(timeout, unit) is exceeded, **TimeoutException** is thrown.

**TimeoutException does not automatically cancel the task**; the task may keep running. With cancel(true), interruption is a cooperative request, not a mechanism to force-stop all work, especially for operations that do not respond to interrupts.

**Limitation of traditional Future:** it provides waiting/cancellation/querying capabilities, but lacks a convenient standard API to register completion callbacks, chain dependent tasks, or transform results without calling get().

## 3. CompletableFuture: A Completable Future with Chained Steps

**CompletableFuture<T>** adds two ideas:

1. **Explicit completion:** complete(value), completeExceptionally(error), and several other completion methods can set the future's state. Only the first normal completion takes effect.
2. **Dependency registration:** thenApply, thenCompose, thenCombine, handle... create downstream stages. When the upstream stage completes, the dependent stage gets a chance to run according to the registered rules.

Common creation patterns:

| Creation Method | How to Understand It |
| --- | --- |
| CompletableFuture.completedFuture(value) | A future already succeeded with value; creates no new task. |
| new CompletableFuture<T>() | An incomplete future; another party must call complete or completeExceptionally. |
| CompletableFuture.supplyAsync(supplier, executor) | Submits value-returning work to executor, returns CompletableFuture<T>. |
| CompletableFuture.runAsync(runnable, executor) | Submits non-value-returning work, returns CompletableFuture<Void>. |

If **supplyAsync/runAsync** are called without an executor, they typically use **ForkJoinPool.commonPool()** under CompletableFuture's default policy; you should not default to using the common pool for long-blocking I/O in server applications. With **new CompletableFuture<>()**, no task is started automatically: forgetting to complete it can leave waiters hung indefinitely.

## 4. Transforming, Chaining, and Combining Multiple Results

| Method | When to Use | Return Type |
| --- | --- | --- |
| thenApply(fn) | Transform result T into U using a regular function. | CompletableFuture<U> |
| thenAccept(action) | Consume the result for a side effect, returning no U. | CompletableFuture<Void> |
| thenRun(action) | Run the next step without needing the previous value. | CompletableFuture<Void> |
| thenCompose(fn) | Next step itself returns a CompletionStage<U>; flattens instead of nesting futures. | CompletableFuture<U> |
| thenCombine(other, fn) | Two independent tasks both succeed, then combine both values. | CompletableFuture<V> |
| allOf(f1, f2, ...) | Wait for all futures to complete; does not collect results into a list automatically. | CompletableFuture<Void> |
| anyOf(f1, f2, ...) | Completes with the first future to complete, even if it failed. | CompletableFuture<Object> |

**thenApply vs. thenCompose:** when the next step returns a plain value, use thenApply; if that step *is itself asynchronous and returns a future*, use thenCompose to avoid CompletableFuture<CompletableFuture<U>>. Similarly, **thenCombine** handles two independent branches, whereas **thenCompose** expresses a sequential dependency (fetch the ID first, then use the ID to load the profile).

Standalone example, save as **CompletableFutureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CompletableFutureDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> price =
                    CompletableFuture.supplyAsync(() -> 100, pool);
            CompletableFuture<Integer> fee =
                    CompletableFuture.supplyAsync(() -> 15, pool);

            CompletableFuture<String> bill = price
                    .thenCombine(fee, Integer::sum)
                    .thenApply(total -> "Total: " + total);

            System.out.println(bill.join());

            CompletableFuture<String> id =
                    CompletableFuture.completedFuture("u-7");
            CompletableFuture<String> profile = id.thenCompose(userId ->
                    CompletableFuture.supplyAsync(
                            () -> "Profile " + userId, pool));

            System.out.println(profile.join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac CompletableFutureDemo.java
java CompletableFutureDemo
~~~

Standard output (the two lines are printed in main's join order, even though worker execution order may vary):

~~~text
Total: 115
Profile u-7
~~~

Dependency diagram:

~~~text
price ──┐
        ├─ thenCombine ─ thenApply ─ bill
fee ────┘

id ─ thenCompose(id -> load profile asynchronously) ─ profile
~~~

The following example is an **illustrative code snippet inside a method**, assuming a and b have type CompletableFuture<String>:

~~~java
CompletableFuture<Void> ready = CompletableFuture.allOf(a, b);
CompletableFuture<java.util.List<String>> both = ready.thenApply(
        unused -> java.util.List.of(a.join(), b.join()));
~~~

After allOf completes normally, both values are ready; the join() calls here merely extract the values. **allOf does not return a List**. If one branch fails, allOf also completes exceptionally and thenApply does not run. For **anyOf**, do not assume the winning branch always succeeded or that it automatically cancels the remaining branches.

## 5. Callback Execution: Without Async vs. With Async

Even though a future describes data flow, **it does not guarantee each stage runs on a separate thread**:

- **thenApply/thenCompose/whenComplete...** (without Async): the callback may run on the thread that completed the previous stage or another thread performing completion. If the stage is already done at registration time, the callback may run immediately on the registering thread. Do not rely on specific thread names.
- **thenApplyAsync(...), thenComposeAsync(...)**: dispatches callback execution to an asynchronous executor. Overloads accepting an executor let you specify a pool explicitly; overloads without an executor use CompletableFuture's default mechanism.
- **supplyAsync(..., executor)**: specifies where the initial supplier runs. A subsequent non-Async thenApply stage is not automatically moved to a new executor.

If a callback does heavy work or blocking I/O, choose an appropriate executor rather than letting it accidentally occupy the thread completing another stage. **Asynchronous does not mean parallel**: a single-threaded pool can still process multiple tasks one after another. Under load, pool size, queue depth, and task rejection policy are key operational factors.

## 6. How Errors Propagate Through a Chain

When a stage throws an exception, that stage completes **exceptionally**. Success-only steps (such as thenApply) are usually skipped, while error-handling steps can recover or observe the failure.

| API | Runs When | Effect |
| --- | --- | --- |
| exceptionally(fn) | When the previous stage fails | Converts the error into a fallback value of the same type T. |
| handle((value, error) -> result) | On success or error | Produces a new value U based on both branches. |
| whenComplete((value, error) -> ...) | On success or error | Observes/logs/records metrics; normally preserves the original result or error. |
| completeExceptionally(error) | When the producer explicitly signals failure | Completes a pending future with an exception. |

Standalone Java 17+ example, save as **FailureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class FailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> original = new CompletableFuture<>();
        original.completeExceptionally(
                new IllegalStateException("Unable to read data"));

        CompletableFuture<Integer> recovered =
                original.exceptionally(error -> 0);

        System.out.println("Fallback value: " + recovered.join());
        System.out.println("Source failed: " + original.isCompletedExceptionally());

        String status = original.handle((value, error) ->
                error == null ? "Success: " + value : "Failed");
        System.out.println(status);
    }
}
~~~

Run:

~~~bash
javac FailureDemo.java
java FailureDemo
~~~

Standard output:

~~~text
Fallback value: 0
Source failed: true
Failed
~~~

Note that **recovered** is a new recovered future; **original** remains failed. **whenComplete** is generally for observation; do not choose it instead of exceptionally/handle when you need to return a fallback. If the error-handling callback itself throws an exception, the new stage can still fail.

**get() vs. join():**

- **get()** is part of the Future API, blocks, and declares checked InterruptedException and ExecutionException; it has a timeout overload. Suitable when explicit interrupt handling is needed.
- **join()** also waits but uses unchecked CompletionException for asynchronous computation failures (or CancellationException when cancelled); convenient when chaining pipelines.
- Do not swallow errors by returning a default value for every failure if doing so hides business issues. Log/contextualize the root cause and decide deliberately whether a fallback is acceptable.

## 7. Timeouts, Cancellation, and Task Lifecycle

Three mechanisms are very easy to confuse:

1. **future.get(500, MILLISECONDS)** bounds *the caller's wait time*. After 500 ms the caller receives TimeoutException, but the future/task may keep running.
2. **future.orTimeout(500, MILLISECONDS)** completes the CompletableFuture itself with TimeoutException if not done by the deadline; the method returns **the same future object**. **completeOnTimeout(fallback, ...)** also acts on that future, completing normally with the fallback instead.
3. **future.cancel(true)** requests cancellation. For standard CompletableFuture, the **mayInterruptIfRunning parameter has no interrupt-control effect**; cancellation is represented as a special completion with CancellationException. This **does not guarantee the background work has stopped**.

This distinction is essential for network calls or queries that can run very long. Future timeouts are coordination-layer deadlines; you must configure appropriate timeouts/interrupts/cancellation on the I/O client or actual execution API to control resources. If you need to stop work, design tasks to check interruption or use the underlying library's cancellation mechanism.

**Never create a future that nobody completes:** a CompletableFuture that never receives complete/completeExceptionally/cancel will cause join() to wait forever. Similarly, calling get()/join() inside a task saturating a pool to wait on another task in the same pool can cause **thread starvation or deadlock**. Express dependencies via thenCompose/thenCombine instead of cross-blocking between workers.

**Do not forget to close self-created executors:** with ExecutorService, call shutdown() when no more tasks will be submitted, then use awaitTermination or an appropriate shutdown policy when the application needs to wait for cleanup. The examples above awaited needed results before shutdown.

## 8. Direct Connection to Spring Framework

Spring provides **TaskExecutor** and **@Async** to run bean methods on an executor. Future/CompletableFuture remains the object type callers receive to track or combine results; @Async controls **where the method runs**, while CompletableFuture helps **how results compose together**.

The following examples are **configuration/service snippets for a Spring application with the Spring Context dependency**; they are not a standalone Java program runnable with two javac/java commands:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {
    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("io-");
        executor.initialize();
        return executor;
    }
}
~~~

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("ioExecutor")
    public CompletableFuture<String> loadReport(String id) {
        // Assume a synchronous data read / I/O task occurs here.
        String content = "report:" + id;
        return CompletableFuture.completedFuture(content);
    }
}
~~~

Another bean calling **reportService.loadReport("r-1")** through the Spring proxy receives a future representing the asynchronous execution of that call; it can attach thenApply/exceptionally instead of waiting immediately. In the example, **completedFuture** is returned from *inside* a method already dispatched to a worker by @Async: there is no need to wrap an already computed result in another supplyAsync.

Constraints when applying this:

- Async support must be enabled (for example **@EnableAsync**) and invoked through the Spring bean/proxy. **Self-invoking an @Async method within the same object** under default proxy configuration bypasses the interceptor and does not switch threads as expected.
- Specify a managed executor; configure pool size, queue, rejection, and shutdown for expected load. I/O pools and CPU pools can have different characteristics.
- **@Async** methods can return **Future** or **CompletableFuture** so callers can track errors; if returning void, errors are not propagated to the caller via a future mechanism (Spring provides AsyncUncaughtExceptionHandler).
- Transactions, SecurityContext, MDC, and ThreadLocal-bound state are **not automatically propagated to another thread in all configurations**. When needed, use a supported context propagation mechanism and define transaction boundaries clearly.
- If a web request calls @Async and then **calls join() immediately on the request thread**, there is still a blocking wait; evaluate true asynchronous response mechanisms at the web layer rather than relying solely on annotations.

A CompletableFuture launched manually via supplyAsync on a plain Java executor **does not automatically become** a Spring @Async method. The two approaches can complement each other without pointless async nesting.

## 9. Common Design Mistakes and How to Spot Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| submit then immediately get() | Caller blocks, little overlapping work. | Do independent work before waiting or use a pipeline. |
| Using thenApply with a future-returning function | Produces nested futures, hard to coordinate. | Choose thenCompose. |
| Assuming isDone() means success | Ignores failures/cancellation. | Check get/join, isCompletedExceptionally, isCancelled as appropriate. |
| Assuming CompletableFuture.cancel(true) stops I/O | Background work may keep consuming resources. | Combine timeouts and cancellation at the task/client layer. |
| Blocking between tasks on a small pool | Worker exhaustion or deadlock. | Compose stages instead of cross-joining; review pool config. |
| Using commonPool for many long I/O tasks | Contention with other work. | Pass a suitable executor and bound load. |
| Swallowing exceptions with a generic fallback | Hides incidents and corrupts data. | Handle deliberately, log root cause, and distinguish fallback errors. |
| Forgetting to complete a manually created future | Callers wait forever. | Define who owns completing every branch, including errors/cancellation. |
| Calling @Async from within the same bean | May bypass the Spring proxy. | Invoke through a Spring-managed bean at the proper boundary. |

## 10. Choosing the Right Tool for the Requirement

- **Only need to submit one computation and eventually wait for the result:** ExecutorService + Future is often sufficient, especially when traditional interrupt/timeout handling is desired.
- **Need to transform or coordinate multiple asynchronous results:** CompletableFuture with thenApply, thenCompose, thenCombine, allOf, and error handling can be much more readable.
- **Need multiple service methods to run off the calling thread in a Spring app:** TaskExecutor + @Async; choose CompletableFuture as the return type when callers need to chain stages.
- **Need deadline and resource control:** deadlines, cancellation policies, and real I/O-layer timeouts are separate design concerns; futures only represent and coordinate state.

## 11. Self-Check Exercises

1. **Predict:** a task threw IllegalStateException; is isDone() true or false? **Answer:** true, because the task completed with an error; get() will throw ExecutionException.
2. **Choose the combinator:** step A returns a user ID; step B calls an async API to load the profile for that ID. **Answer:** thenCompose, because B returns a new stage depending on A.
3. **Two independent requests returning price and fee:** want to compute the sum when both succeed. **Answer:** thenCombine; if waiting on multiple requests without directly combining values, allOf.
4. **get(timeout) throws TimeoutException:** is the task cancelled? **Answer:** not automatically.
5. **Calling cancel(true) on a CompletableFuture:** is the worker guaranteed to be interrupted? **Answer:** no; the parameter does not control interruption in the standard CompletableFuture implementation.
6. **An @Async method called via this.loadReport():** is it guaranteed to run on the executor? **Answer:** no in standard Spring proxy mode, because self-invocation bypasses the proxy.

## 12. Key Takeaways

**Future** is a promise that submitted work *will have a result or error*; direct usage primarily involves checking state and waiting. **CompletableFuture** is also a completion point and a dependency graph: it lets you express **when A is ready, do B**, **when both A and B are ready, combine them**, and **when an error occurs, recover**, without blocking at every step. Even so, **executor scheduling, resource limits, I/O timeouts, and actual cancellation mechanisms** must still be designed separately. In Spring, @Async routes method execution through TaskExecutor; CompletableFuture helps callers compose those results.

**API docs to consult:** Java SE 17 java.util.concurrent.Future, CompletionStage, CompletableFuture; Spring Framework Reference, Task Execution and Scheduling and @Async sections.
