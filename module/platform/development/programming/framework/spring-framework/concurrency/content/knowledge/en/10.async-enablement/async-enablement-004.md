# void, Future, and CompletableFuture Return Types of @Async in Spring Framework

`@Async` allows Spring to hand off a method call to an executor so the work executes asynchronously. However, the method's **return type** determines whether the caller receives completion signals, results, and exceptions. With the Spring Framework, the three most common types are **`void`**, **`Future<T>`**, and **`CompletableFuture<T>`**. They differ not only in syntax, but also in how processing flows are structured, how errors are observed, and how timeouts, cancellation, and multi-task coordination work.

This lesson belongs to the **Enabling `@Async`** group: it focuses on return type contracts when using Spring proxies, proper implementation, and how callers consume results. The examples use Java 17+ and Spring Framework 6.x; the Spring code requires the `spring-context` dependency, while pure Java examples can be compiled with the JDK.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why an `@Async` method should only declare `void` or a Spring-supported `Future` type, and cannot simply be changed to return `String`, `int`, or `ResponseEntity` while expecting the proxy to act as a value-returning async call.
- Choose `void` when no return result is needed, and understand how errors are reported via `AsyncUncaughtExceptionHandler`.
- Return `Future<T>` when callers need results via `get()`, and handle `ExecutionException`, `TimeoutException`, and `InterruptedException`.
- Use `CompletableFuture<T>` to apply `thenApply`, `thenCompose`, `thenCombine`, `allOf`, `handle`, and `exceptionally`, and observe failures.
- Understand the difference between a **temporary Future inside the target method** and the **actual Future from the Spring proxy**.
- Distinguish errors **at task submission time** from errors **occurring inside the task**, as well as the effects of timeouts, cancellation, and executor saturation.
- Avoid self-invoking `@Async` within the same bean, avoid unnecessary thread blocking, and avoid misunderstandings about `CompletableFuture.completedFuture` or `supplyAsync`.

## 2. Conditions for @Async to Actually Work

`@Async` is a Spring annotation, not a Java keyword that spawns threads on its own. In common usage, Spring registers an interceptor through `@EnableAsync` and creates a proxy around the bean. When another bean calls the method **through the proxy**, the interceptor selects an executor and submits a task to that executor. The client call normally returns without waiting for the worker's portion to finish; exceptions include executors that run directly on the caller or special policy configurations.

Conceptual model:

~~~text
Caller thread
  |
  | calls asyncService.compute(...)
  v
Spring proxy / @Async interceptor
  |
  | submits Callable/Runnable to executor
  +-------------------------------+
  |                               |
  | returns void or Future        v
  |                          Worker thread
  |                           runs target method
  |                           completes or fails
  v                               |
Caller can do other work          |
  |                               |
  +---- Future / callback <-------+
~~~

For this model to hold:

1. Enable `@EnableAsync` in the application configuration (Spring Boot can also use it to activate annotation-driven async).
2. Use a Spring-managed bean and call through the proxy; `public` methods that can be overridden/intercepted are the clearest choice.
3. Configure the executor explicitly; it can be specified with `@Async("reportExecutor")`.
4. Avoid `this.methodAsync()` inside the same bean under the default proxy mode: internal calls bypass the proxy and run as ordinary Java methods.
5. Avoid placing `@Async` on `private` or `final` methods expecting regular proxy mode to intercept the call. `@Async` is not supported on methods declared inside a `@Configuration` class.

**Return type contract limits:** with `@Async` in Spring Framework 6.x, the method declaration should be `void` or a framework-supported `java.util.concurrent.Future` type, including `CompletableFuture`. Older Spring versions also supported `ListenableFuture` (a deprecated API); in modern Java code, `CompletableFuture` is generally a better fit. A synchronous method can return `String` directly, but that method is not a valid signature for the `@Async` interceptor to return a value asynchronously.

## 3. Three Return Types: Quick Comparison Table

| Criterion | `@Async void` | `@Async Future<T>` | `@Async CompletableFuture<T>` |
| --- | --- | --- | --- |
| Caller receives immediately | No result handle | A `Future<T>` | A `CompletableFuture<T>` |
| Reading final value | Impossible through this call | `get()` | `get()`, `join()`, or callbacks |
| Observing completion | Requires logs/metrics/state or external signal | `isDone()`, `get()` | `isDone()`, `whenComplete()`, completion chain |
| Observing exceptions in body | `AsyncUncaughtExceptionHandler` | `get()` throws `ExecutionException` | Completes exceptionally; `join()` typically throws `CompletionException` |
| Non-blocking transformation chain | No result to chain | No standard chaining API | `thenApply`, `thenCompose`, `thenCombine`, ... |
| Cancellation | No `Future` for caller to cancel | `cancel(...)` | `cancel(...)` and completion methods |
| Main risk | Errors don't reach caller; easy "fire-and-forget" silent loss | `get()` can block | Complex callback/exception chains; still risks blocking |
| Typical scenario | Best-effort telemetry/signaling | Integrating legacy APIs needing results | Orchestrating multi-step async flows, returning results to other services |

Do not choose `void` just to avoid writing error-handling code. For work that must be guaranteed to finish, whichever return type you pick, you still need persistent state and proper retry/recovery mechanisms.

## 4. @Async void: No Result Channel for the Caller

A method like:

~~~java
@Async("lessonExecutor")
public void sendAudit(String event) {
    auditRepository.save(event);
}
~~~

This is an **illustrative snippet** inside a Spring-managed bean that has `auditRepository`; it does not run standalone. When a caller invokes it through the proxy and the executor accepts the work, the caller typically does not wait for the repository save to finish. Because the method returns `void`, the caller has no `get()`, `join()`, `isDone()`, or cancellation API.

An error in the body—such as `auditRepository.save` throwing an exception—occurs while the task is running. With `void`, Spring has no Future to propagate the error back to the caller, so it passes the unhandled exception to **`AsyncUncaughtExceptionHandler`**. By default, errors are usually logged; a custom handler can be provided via `AsyncConfigurer`.

### Configuring a Handler for void Errors

~~~java
import java.lang.reflect.Method;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (Throwable exception, Method method, Object... params) -> {
            System.err.println(
                    "Async void failed in " + method.getName()
                    + ": " + exception.getClass().getSimpleName());
        };
    }
}
~~~

This is a **Spring configuration class** requiring Spring libraries; it is not standalone Java SE. Real applications should use controlled logging/metrics/correlation IDs and avoid printing full `params` if they contain sensitive data. The handler should execute quickly and not throw secondary errors.

**`AsyncUncaughtExceptionHandler` does not turn an exception into a response for the caller.** If an API needs to report "job succeeded/failed" to users, use `Future`/`CompletableFuture` or a job ID pointing to persistent status. The handler also does not replace handling **`TaskRejectedException` when a task fails to submit**: rejection can occur right when the proxy submits the work, before the body ever runs.

### When Is void Appropriate?

- Very short tasks where loss is acceptable by contract and logging/metrics are already in place.
- Emitting an internal best-effort event that has an independent error-handling path.
- Triggering a workflow whose state is managed elsewhere, such as a job table; in that case `void` is merely a dispatch interface, not proof of completion.

Do not use `@Async void` to promise that financial transactions, critical emails, or order updates will definitely execute. An in-memory executor queue provides no durability guarantee.

## 5. @Async Future<T>: Receiving a Handle and Explicitly Awaiting the Result

Java's `Future<T>` represents a computation whose result becomes available in the future. Callers can use:

- `get()`: waits indefinitely until completion; when the task fails, throws `ExecutionException` with `getCause()` holding the root cause.
- `get(timeout, unit)`: waits up to the specified duration; throws `TimeoutException` upon expiration.
- `isDone()`: indicates whether the Future has terminated in any way (success, error, or cancellation), **not** success exclusively.
- `cancel(mayInterruptIfRunning)` and `isCancelled()`: requests/reports cancellation status; the actual effect depends on the implementation and whether the task cooperates with stopping.

With `@Async Future<T>`, the caller receives a Future from the **proxy**. The target method must preserve the `Future<T>` signature, so inside the target method it returns a **temporary Future** wrapping the newly computed value. A simple approach in Java 17 is `CompletableFuture.completedFuture(value)`, which is assignable to `Future<T>`.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class UserLookupService {

    @Async("lessonExecutor")
    public Future<String> lookup(int userId) {
        // Simulates actual blocking work; here it just builds a string.
        String value = "user-" + userId;
        return CompletableFuture.completedFuture(value);
    }
}
~~~

**Important:** the `completedFuture(value)` call above executes **inside the thread running the target method**; it satisfies the target's return type signature. The Future that the **caller sees through the Spring proxy** is a handle representing the actual task submitted to the executor and may not yet be complete. It is not a guarantee that the entire `@Async` call finished synchronously at the caller.

An older Spring idiom is `new AsyncResult<>(value)`; in modern documentation, `CompletableFuture.completedFuture(value)` is usually clear enough without an extra helper class.

### Caller Retrieving the Result and Handling Exceptions

The snippet below is **illustrative code inside another service/controller** that injects `UserLookupService userLookupService`, not standalone code:

~~~java
Future<String> future = userLookupService.lookup(7);

try {
    String user = future.get(2, TimeUnit.SECONDS);
    System.out.println(user);
} catch (TimeoutException ex) {
    // Timeout only limits wait time; does not stop the worker automatically.
    future.cancel(true);
} catch (ExecutionException ex) {
    // Error inside the worker is in ex.getCause().
    throw new IllegalStateException("Lookup failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Delegate cancel/exit decision back to the calling layer.
}
~~~

Imports for `java.util.concurrent.*` or the specific classes are needed. `Future.get()` is **blocking**: if you call it right after `lookup()` on a request thread and wait for completion, you still block the thread serving the request. Offloading work to a worker does not automatically make the whole request non-blocking.

`get(timeout)` throwing `TimeoutException` does not mean the task was cancelled or will never succeed; timeout is a state of the **waiter**, not the execution state of the work. `cancel(true)` may request interruption of a running task on standard Futures, but the task must respond to interruption and blocking libraries must support it; there is no guarantee of halting side effects that have already begun.

### Future<T> Has No Direct Chaining

`Future` only provides APIs to wait, inspect, and cancel. It does not directly provide `thenApply` or `thenCompose`. Therefore, when multiple sequential transformations are needed, callers often have to block with `get()` or manage extra callbacks/workers themselves. This is why `CompletableFuture` is usually more convenient in modern Spring code.

## 6. @Async CompletableFuture<T>: Results and Composition

`CompletableFuture<T>` implements both `Future<T>` and `CompletionStage<T>`. It lets you describe **what to do when a result arrives**, rather than always forcing the caller to wait.

Spring method template:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    @Async("lessonExecutor")
    public CompletableFuture<Integer> doublePrice(int price) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        int calculated = price * 2;
        return CompletableFuture.completedFuture(calculated);
    }
}
~~~

This is a **Spring service** requiring a valid proxy and executor. Inside the target method, `completedFuture(calculated)` merely creates a temporary handle matching the signature. When called from another bean through the proxy:

~~~java
CompletableFuture<Integer> result = pricingService.doublePrice(21);

CompletableFuture<String> rendered =
        result.thenApply(value -> "price=" + value);
~~~

`rendered` represents the chained computation; the caller can return it to another layer instead of blocking. The successful value upon completion will be `price=42`. If `doublePrice(-1)` throws an exception on the worker, the future from the proxy completes **exceptionally**, rather than returning a successful `Integer` value.

### Why Shouldn't You Always Call supplyAsync Inside @Async?

This is an approach that easily causes confusion:

~~~java
@Async("lessonExecutor")
public CompletableFuture<String> fetch() {
    return CompletableFuture.supplyAsync(() -> remoteCall());
}
~~~

The snippet above is **non-standalone illustrative code**, with `remoteCall()` supplied by the application. `@Async` has already handed the target method off to an executor. Calling `supplyAsync` without passing an executor dispatches the work onward to **`ForkJoinPool.commonPool()`** by default, introducing an extra scheduling layer and complicating thread pool control, context propagation, cancellation, and error visibility. If you need to compose multiple stages, design each executor and thread-hop intentionally; if you only compute one result inside an `@Async` method, returning `CompletableFuture.completedFuture(value)` once done is usually sufficient.

This does **not** mean `CompletableFuture.supplyAsync` is always wrong. It is very useful in plain Java code or in services not using `@Async`, when you explicitly own the executor and want to construct an asynchronous pipeline.

## 7. Key CompletableFuture Combinators

| API | Contract | When to Use |
| --- | --- | --- |
| `thenApply(fn)` | Transforms value `T -> U`; result is a new stage | Mapping, formatting, short computations |
| `thenCompose(fn)` | Awaits a stage returned by `fn` and flattens the result | Next step depends on previous result and is itself async |
| `thenCombine(other, fn)` | Combines two independent futures once both complete normally | Merging profile and preferences |
| `allOf(f1, f2, ...)` | Aggregate future completes when all futures complete | Waiting on a batch of jobs; read individual results after success |
| `anyOf(f1, f2, ...)` | Completes with the first future to finish | Racing tasks; does not automatically cancel remaining tasks |
| `whenComplete((v, ex) -> ...)` | Runs an observation callback for value/error, preserving original outcome if callback doesn't fail | Metrics, logging, observational cleanup |
| `handle((v, ex) -> r)` | Transforms both success and error paths into a new result | Intentionally converting an error into a fallback value |
| `exceptionally(ex -> fallback)` | Provides a replacement value on error | Safe fallback when business rules permit |

### thenApply vs. thenCompose: Avoiding Nested Futures

Suppose `profileService.load(id)` returns `CompletableFuture<Profile>` and `scoreService.score(profile)` returns `CompletableFuture<Integer>`. The `Profile` type and services here are **conceptual placeholders** of a system, not a standalone runnable example.

Wrong intent when wanting a single final future:

~~~java
CompletableFuture<CompletableFuture<Integer>> nested =
        profileService.load(id)
                .thenApply(profile -> scoreService.score(profile));
~~~

`thenApply` only transforms the value and keeps the new Future as the **value** of the outer stage. Use `thenCompose` to flatten:

~~~java
CompletableFuture<Integer> score =
        profileService.load(id)
                .thenCompose(profile -> scoreService.score(profile));
~~~

If two tasks are independent, they can execute concurrently and then be combined:

~~~java
CompletableFuture<String> description =
        nameService.loadName(id)
                .thenCombine(scoreService.loadScore(id),
                        (name, score) -> name + ":" + score);
~~~

These snippets use hypothetical services to illustrate composition APIs; the corresponding interfaces/services are needed to compile. Be sure to observe exceptions from **both sources** and avoid blocking with `join()` inside callbacks running on the same small-worker executor.

### allOf Does Not Automatically Produce a List<T>

`CompletableFuture.allOf(a, b)` returns `CompletableFuture<Void>`: it is an aggregate completion signal, not a `List<T>`. Once all complete successfully, you can retrieve each future's result. If one future completes exceptionally, the aggregate future may also complete exceptionally. If you want to surface individual job errors, handle them before combining.

Illustrative example only with futures `a` and `b` of type `CompletableFuture<String>`:

~~~java
CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
CompletableFuture<String> summary =
        all.thenApply(ignored -> a.join() + ", " + b.join());
~~~

`join()` inside the callback only reads results that have already completed successfully because `allOf` preceded it; do not use `join()` indiscriminately inside a worker when it might have to wait on another task not yet scheduled.

## 8. Exceptions: void, Future, and CompletableFuture Propagate Errors Through Different Channels

Suppose a target method throws `IllegalArgumentException`. How callers observe it depends on the return type:

| Method | Channel for Observing Body Errors | How to Handle |
| --- | --- | --- |
| `@Async void` | `AsyncUncaughtExceptionHandler` when task runs via interceptor | Logs, metrics, persistent business state |
| `@Async Future<T>` | Future completes with error; `get()` throws `ExecutionException` | Read `getCause()`, classify error, fallback or fail |
| `@Async CompletableFuture<T>` | Future completes exceptionally | `handle`, `exceptionally`, `whenComplete`, or `join/get` |
| Rejection before task runs | May throw `TaskRejectedException` right at the proxy call | Handle submit rejection, report overload/persist retry |

Error-handling example with `CompletableFuture`:

~~~java
CompletableFuture<Integer> future = pricingService.doublePrice(-1);

CompletableFuture<String> message =
        future.handle((value, error) -> {
            if (error != null) {
                return "calculation failed";
            }
            return "result=" + value;
        });
~~~

This is an **illustrative snippet**, requiring `pricingService` as an injected Spring bean. `handle` converts even the error path into a successful string; this should only be done if a fallback is an allowed business behavior. If you need to preserve the error for upstream layers, `whenComplete` is usually better for logging/metrics without swallowing the exception.

### get() vs. join(): Different Exception Types

`Future.get()` (including when called on a `CompletableFuture`) can throw:

- `InterruptedException` if the waiting thread is interrupted.
- `ExecutionException` if the computation failed; the underlying cause is in `getCause()`.
- `TimeoutException` on the `get(timeout, unit)` overload if the wait deadline expires.
- `CancellationException` if the future was cancelled.

`CompletableFuture.join()` declares no checked exceptions; when computation fails, it typically throws `CompletionException` with the root error as its cause, and when cancelled, it throws `CancellationException`. **Do not treat `join()` as "non-blocking"**: it still blocks until completion if the future is not yet done.

Error-catching pattern:

~~~java
try {
    int result = future.join();
    System.out.println(result);
} catch (CompletionException ex) {
    Throwable original = ex.getCause();
    System.err.println("Task failed: " + original);
} catch (CancellationException ex) {
    System.err.println("Task was cancelled");
}
~~~

This is an **illustrative snippet** with variable `future` of type `CompletableFuture<Integer>`; imports for `java.util.concurrent.CompletionException` and `CancellationException` are required.

### Errors Can Arrive Immediately When Calling @Async

If the executor is overloaded and uses `AbortPolicy`, Spring's `ThreadPoolTaskExecutor` typically raises `TaskRejectedException` **immediately when submitting through the proxy**, before any `Future` is returned to the caller. Therefore, if the caller must handle work non-acceptance, catch it at the method call boundary:

~~~java
try {
    CompletableFuture<Integer> result = pricingService.doublePrice(21);
    // Only handle result after receiving the Future.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Executor did not accept the task under the active policy.
}
~~~

This snippet does not run standalone and must not be confused with `IllegalArgumentException` thrown **inside the body** of `doublePrice`. If the policy is `CallerRunsPolicy`, submission may run inline and block the caller; if `DiscardPolicy`, the task may be dropped silently. A Future return type cannot fix the ambiguity created by a policy that drops tasks without reporting an error.

## 9. Timeout, Cancellation, and Interruption: Levels of Guarantees

| Tool | Meaning | What Must Not Be Inferred |
| --- | --- | --- |
| `future.get(2, SECONDS)` | Caller waits at most two seconds | Does not mean the worker stops at second two |
| `future.cancel(true)` | Requests cancellation; on some Futures, may ask to interrupt the task | Not guaranteed that side effects stopped |
| `future.isCancelled()` | Future is marked cancelled | Does not prove I/O rolled back |
| `CompletableFuture.orTimeout(2, SECONDS)` | Completes that CompletableFuture exceptionally if not done after the specified time | Does not automatically interrupt work running on the executor |
| `CompletableFuture.completeOnTimeout(default, 2, SECONDS)` | Completes with default value on timeout | Does not ensure the background task stops running |
| `CompletableFuture.cancel(true)` | Marks `CompletableFuture` as cancelled | `mayInterruptIfRunning` is not used to control worker interruption |

`CompletableFuture` is a completion model; attaching timeout/cancel to the handle **does not mean** you hold authority to stop the actual thread. For tasks that must stop on time, apply deadlines to I/O clients, transactions, and processing logic; design cancellation tokens, cooperative interruption, or idempotency where appropriate.

Note: `orTimeout` and `completeOnTimeout` mutate/return **the same CompletableFuture** per the API contract, so multiple consumers sharing one future may all be affected by that timeout. When you do not want to mutate the source, intentionally create a separate stage, while understanding stage propagation/cancellation semantics.

### If You Wait on a Future Inside a Request Thread

Calling `@Async` and then `future.get()` immediately in a controller can make the entire request wait. There can be reasons for this when you need to enforce a timeout and return a result in the request, but measure thread occupancy and deadlines. If the application uses asynchronous HTTP response mechanisms, consider returning `CompletableFuture` via framework-supported integration instead of blocking yourself; that is a separate web interaction topic, not applied automatically to every method.

## 10. Standalone Java 17+ Code to Practice Future and CompletableFuture

The example below uses plain Java `ExecutorService`, **without Spring**, to solidly verify the semantics of `Future`, `CompletableFuture`, and a task that returns no result to the caller. Afterward, we will compare it with `@Async` in Spring.

File **FutureModesDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureModesDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "ready";
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            System.out.println("pending=" + !future.isDone());
            release.countDown();
            System.out.println("future=" + future.get(5, TimeUnit.SECONDS));

            CompletableFuture<Integer> doubled =
                    CompletableFuture.supplyAsync(() -> 21, executor)
                            .thenApply(value -> value * 2);
            System.out.println("composed=" + doubled.get(5, TimeUnit.SECONDS));

            CompletableFuture<Integer> failed =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalArgumentException("invalid");
                    }, executor);

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println(
                        "cause=" + ex.getCause().getClass().getSimpleName());
            }

            CountDownLatch voidCompleted = new CountDownLatch(1);
            executor.execute(voidCompleted::countDown);
            if (!voidCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Void task did not finish");
            }
            System.out.println("voidTaskDone=true");
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac FutureModesDemo.java
java FutureModesDemo
~~~

Deterministic stdout under successful execution:

~~~text
pending=true
future=ready
composed=42
cause=IllegalArgumentException
voidTaskDone=true
~~~

Explanation:

1. `started.await()` proves the task has been picked up by the worker and is waiting on `release`, so when reading `future.isDone()` the result cannot yet be finished: `pending=true`.
2. `release.countDown()` lets the worker return `"ready"`, and `future.get(5,...)` returns the expected value.
3. `supplyAsync` runs a computation on the passed-in executor; `thenApply` turns `21` into `42`.
4. A computation throwing `IllegalArgumentException` causes the future to complete exceptionally; `join()` wraps the error in `CompletionException`, whose cause reflects the original error.
5. The task passed to `execute` has no return value; the example uses an independent latch to confirm `voidTaskDone=true`, because `execute` itself provides no Future.

Moving to Spring, `@Async` handles routing the method call through a proxy and submitting the task to an executor, while the JDK's `Future`/`CompletableFuture` contracts are still used to observe outcomes. **Do not blindly copy `supplyAsync` into every `@Async` method just because this is a plain Java demo.**

## 11. Spring Configuration for the Three-Return-Types Example

Below is a concise configuration for a Spring Framework application with `spring-context`. The thread pool sizes are illustrative only; in real deployments, measure load and tune queue/rejection limits accordingly.

File **LessonAsyncConfig.java**:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class LessonAsyncConfig {

    @Bean(name = "lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("lesson-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

File **LessonAsyncService.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LessonAsyncService {

    @Async("lessonExecutor")
    public void publishNotice(String text) {
        if (text.isBlank()) {
            throw new IllegalArgumentException("blank notice");
        }
        System.out.println("Notice: " + text);
    }

    @Async("lessonExecutor")
    public Future<String> loadName(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("invalid id");
        }
        return CompletableFuture.completedFuture("user-" + id);
    }

    @Async("lessonExecutor")
    public CompletableFuture<Integer> calculateScore(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
        return CompletableFuture.completedFuture(value * 10);
    }
}
~~~

These are **two separate Spring Java files** without `main` and need to be component-scanned/imported by an ApplicationContext. Thanks to `@EnableAsync` and `@Async("lessonExecutor")`, calls through the bean proxy submit work to the executor named `lessonExecutor`. `publishNotice` fits demoing a no-result task; `loadName` returns a value via Future; `calculateScore` returns a CompletableFuture for further composition. The example is intentionally simple and contains no database queries or side effects requiring durability.

File **LessonAsyncConsumer.java** for another bean calling the service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class LessonAsyncConsumer {

    private final LessonAsyncService worker;

    public LessonAsyncConsumer(LessonAsyncService worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> start(int id) {
        return worker.calculateScore(id)
                .thenApply(score -> "score=" + score);
    }
}
~~~

`start(3)` gives the caller a future that, upon normal completion, holds `"score=30"`. It does not call `get()` or `join()` inside the service, so it does not block waiting for the result itself. Each file has the exact class name shown in the example. When running in Spring Boot, place them in a component-scanned package, or declare/import the corresponding beans.

**To use a plain Future:** another bean can call `worker.loadName(3)` and then `get(timeout)` at the boundary where the value is genuinely needed. Do not call `get` right inside the same worker thread when waiting depends on another task queued on that exact same pool; on a small pool, starvation or deadlock can occur.

## 12. "Temporary Future" and "Proxy Future" Are Not the Same Object

A common point of confusion is target code like:

~~~java
@Async("lessonExecutor")
public CompletableFuture<String> greeting() {
    String value = slowOperation();
    return CompletableFuture.completedFuture(value);
}
~~~

`slowOperation()` here is a **hypothetical method** called on an executor worker; this snippet is not standalone. There are two phases:

1. **Caller** invokes proxy `greeting()`; Spring creates/submits a task and returns a **Future representing that work**.
2. **Worker** runs the target method, calls `slowOperation()`, and creates the temporary `completedFuture(value)`. Spring takes the value/status from the temporary handle and completes the representative handle held by the caller.

In a system with long-running work, the caller can see `future.isDone()==false` even though `return CompletableFuture.completedFuture(value)` appears in the target code. That return statement does not execute until the work inside the method finishes.

Avoid the misconception that "Spring `@Async` is useless because the method returns `completedFuture`." `completedFuture` plays the role of **satisfying the signature on the target**, while calling through the proxy establishes the async contract for the client.

If you call `this.greeting()` inside the target class itself, **the proxy is bypassed**; in that case you directly receive the completedFuture created by the target, and `slowOperation()` runs immediately on the calling thread without the expected asynchronicity.

## 13. Synchronous or Asynchronous Chaining: thenApply vs. thenApplyAsync

`CompletableFuture.thenApply(fn)` does not require creating a new thread. The callback may run on the thread completing the preceding stage or the thread registering the callback if the stage is already complete; do not rely on a specific thread name. If the callback is heavy, it may tie up the worker completing other work.

`thenApplyAsync(fn)` schedules the callback onto an executor. If **no executor is passed**, Java typically uses `ForkJoinPool.commonPool` for async completion methods; this may differ from the configured `@Async` pool.

~~~java
CompletableFuture<String> formatted =
        worker.calculateScore(3)
                .thenApplyAsync(
                        score -> "score=" + score,
                        formattingExecutor);
~~~

This is an illustrative snippet inside a bean with injected `worker` and `formattingExecutor` (of type `Executor`). When picking a separate executor, you must manage pool size, queue, rejection, shutdown, and context propagation on **both**. If the callback is short, `thenApply` may suffice. If the callback is blocking or CPU-heavy, consider `thenApplyAsync` with an appropriate executor.

Do not assume `thenApplyAsync` is always faster; it adds scheduling overhead, can hit `RejectedExecutionException` if the callback executor declines work, and can raise total concurrency unexpectedly.

## 14. @Async and Transactions, ThreadLocal, and MDC

Executing on another thread means many contexts bound to the submitting thread **are not inherited automatically**:

- Transaction resources/`@Transactional` are typically thread-bound; an `@Async` method running on its own thread does not automatically inherit the caller's transaction. If the worker needs its own transaction, define an appropriate boundary for that work.
- Security context, MDC/trace context, and other `ThreadLocal` values usually require intentional propagation (`TaskDecorator`, framework mechanisms, or immutable data passed as arguments).
- A `thenApply` callback may run on a different thread from where it was registered; do not rely on implicit ThreadLocals to drive critical business logic.

If `@Async` is called inside a transaction before commit, the worker may run before the data it needs to read has committed. For requirements like "only run after the transaction succeeds," consider after-commit event processing or a **transactional outbox** if durability across application crashes is required.

Another mistake: putting `@Transactional` on an `@Async` method and thinking the caller's transaction is carried over. In reality, interception, transaction opening, and execution threads must be designed/tested according to advice ordering; do not rely on assumptions.

## 15. Under Increasing Load: Return Type Does Not Guarantee Task Acceptance

`@Async` requires an executor with enough capacity. If the pool saturates or has shut down:

- `AbortPolicy` typically throws `TaskRejectedException` via `ThreadPoolTaskExecutor` at submit time; the caller must handle the case where **work was not accepted**, and there may not be any `Future` to wait on.
- `CallerRunsPolicy` can make the task run **right on the caller thread** when the pool saturates: even with `@Async`, the call can take as long as the body, breaking fast-response expectations.
- `DiscardPolicy` can drop tasks silently; the `Future` may never complete if discarded without cancellation.
- During shutdown, `CallerRunsPolicy` can silently drop tasks per JDK behavior, no longer running on the caller.

**Do not confuse a `Future` with a durability promise.** A task accepted into an in-memory queue can be lost if the process dies. If you must guarantee processing of reports, critical notifications, or orders, use a durable job table/queue, retries, idempotency, and queryable state.

Especially for HTTP 202 Accepted: only confirm "accepted" to the extent the application truly guarantees. Without a durable job store, the response must not promise processing will survive a restart.

## 16. Is Your @Async Test Reliable?

Do not use `Thread.sleep(100)` and assume the worker has finished. Better approaches:

1. **Proper proxy**: inject the `@Async` bean from another bean/test; do not call methods directly on `new LessonAsyncService()` thinking you tested Spring.
2. **Future/CompletableFuture**: assert values using `get(timeout, unit)` so tests don't hang; assert the root cause when `get` throws `ExecutionException` or `join` throws `CompletionException`.
3. **void**: use `CountDownLatch` or a thread-safe recorder/metric to confirm completion; test the `AsyncUncaughtExceptionHandler` path separately.
4. **Submit failures**: create a 1-worker + 1-queue pool, use a latch to hold the worker so the queue fills, then submit another task and verify rejection at the caller.
5. **Timeout/cancel**: control timing with latches, verify how the future transitions states, and check whether the task actually stops.
6. **Thread context**: verify transaction/MDC/security context across worker, caller-runs, or selected callback threads.
7. **Shutdown**: test tasks accepted but not yet started, cancellation, queue draining, and retries from durable storage.

**Illustrative** JUnit 5 example (requires Spring bean classes, test context, and corresponding imports):

~~~java
CompletableFuture<Integer> task = lessonAsyncService.calculateScore(4);
assertEquals(40, task.get(2, TimeUnit.SECONDS));

CompletableFuture<Integer> bad = lessonAsyncService.calculateScore(-1);
ExecutionException error = assertThrows(
        ExecutionException.class,
        () -> bad.get(2, TimeUnit.SECONDS));
assertInstanceOf(IllegalArgumentException.class, error.getCause());
~~~

The example requires `assertEquals`, `assertThrows`, and `assertInstanceOf` from JUnit Jupiter and `lessonAsyncService` injected **via a Spring context**. This is not a complete JUnit file, so there is no standalone `javac` command. The goal is asserting results/errors rather than depending on sleep durations.

## 17. Common Mistakes and Fixes

1. **Annotating `@Async` and declaring return type `String`.** Return type is incompatible with the interceptor; return `Future<String>` or `CompletableFuture<String>`.
2. **Missing `@EnableAsync`, not using a Spring bean, or calling `this.method()` internally.** Proxy does not run, and the call can become synchronous.
3. **Using `void` for work whose outcome must be known.** Caller gets no signal; replace with Future or durable job status.
4. **Assuming exceptions in `@Async void` throw back to the controller like synchronous errors.** Body errors pass through `AsyncUncaughtExceptionHandler` on the normal path.
5. **Calling `get()` right after submission on a request thread.** Caller blocks again; only wait when truly necessary and with a deadline.
6. **Not handling `InterruptedException` properly.** Typically restore the flag with `Thread.currentThread().interrupt()` if not rethrowing, then cancel/exit per contract.
7. **Equating `isDone()` with success.** A failed or cancelled Future still has `isDone()==true`.
8. **Confusing `TimeoutException` with the worker stopping.** A waiter's timeout does not automatically cancel or roll back the task.
9. **Confusing `CompletableFuture.cancel(true)` with guaranteed interruption.** That parameter does not control interruption like a traditional `FutureTask`.
10. **Using `supplyAsync` inside every `@Async` method.** Can create two-tier scheduling and misuse commonPool.
11. **Using `thenApply` on a Future-returning function and getting a nested Future.** Use `thenCompose` when the next step is also async.
12. **Using `exceptionally` to return a fallback for every error and hiding business failures.** Fallbacks must be intentionally designed, logged/monitored, and classified properly.
13. **Blocking on `join()` inside a callback running on a small-thread executor.** Can deadlock the entire pool when waiting on another task needing that same pool.
14. **Relying on request context/transactions inside a worker.** Thread-bound state does not transfer automatically.
15. **Ignoring `TaskRejectedException` at the call boundary.** The task may not have been accepted; do not return a fake "processed" response.
16. **Assuming CompletableFuture makes everything non-blocking.** A Future is a handle; the body can still block a worker, callbacks can run inline, and `join/get` still blocks the caller.
17. **Not measuring queues, active threads, timeouts, or completion failures.** Under overload, latency spikes and lost tasks appear before overall metrics flag an issue.
18. **Assuming an exception from a Future task goes through `AsyncUncaughtExceptionHandler` like `void`.** With Future, the error is stored in the Future and must be handled by the consumer.

## 18. Which Type to Choose in Practice?

| Requirement | Good Initial Choice | Notes |
| --- | --- | --- |
| Best-effort telemetry logging, no return value needed | `void` | Must observe errors and define event-loss policy |
| Returning a result from a legacy API that needs waiting | `Future<T>` | Caller uses `get(timeout)`; avoid blocking latency-sensitive threads |
| Transforming results in a multi-step pipeline | `CompletableFuture<T>` | `thenApply/thenCompose` and exceptional completion handling |
| Combining two independent data sources | `CompletableFuture<T>` | `thenCombine` or `allOf`, manage errors on both branches |
| System needing explicit cancellation/timeouts | `Future` or `CompletableFuture` with cancellation protocol | Handle alone does not guarantee thread stops or side effects roll back |
| Job that must not be lost across restarts | Job ID + durable queue/job store, optionally paired with `CompletableFuture` for current request | In-memory Future is not the source of truth |
| API wanting to return HTTP response asynchronously | `CompletableFuture<T>` in appropriate integration | Must consider web framework behavior and client deadlines |

No single return type fits every problem. The choice should be based on the **meaning of the result**, **who needs to know about errors**, **how callers wait or compose**, **deadlines**, and **the contract when the executor refuses the task**.

## 19. Self-Check Questions

1. Why is `@Async public String load()` not a valid asynchronous value-returning signature for a Spring proxy?
2. With `@Async void`, where are exceptions inside the worker observed? Why can't a controller usually catch them directly?
3. Inside the target method, why can it return `CompletableFuture.completedFuture(value)` while the caller still receives an incomplete Future?
4. Does `Future.get(2, SECONDS)` timing out guarantee the task has stopped?
5. What is the difference between `Future.get()` and `CompletableFuture.join()` regarding exception types when a task fails?
6. When should you use `thenCompose` instead of `thenApply`?
7. Why can calling `CompletableFuture.supplyAsync(...)` without an executor inside an already-`@Async` method make code hard to control?
8. If `@Async("lessonExecutor")` hits pool rejection before submission, will the caller receive a Future? How should you report the error?
9. Why does calling `this.calculateScore(3)` within the same bean fail to prove the method runs asynchronously?
10. If an `@Async CompletableFuture` method needs a transaction and access to security context, which boundaries do you inspect?
11. Does `CompletableFuture.cancel(true)` guarantee interrupting an in-flight HTTP call?
12. For a job that must be guaranteed to complete after an application restart, what component must be combined with Future?

## 20. Official References

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.1 — @Async API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework 6.1 — @EnableAsync API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.1 — AsyncConfigurer API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

**Remember:** `void` gives callers no result channel; `Future` provides a handle to wait, check status, and cancel; `CompletableFuture` adds composition and callback-based error handling. **`@Async` determines how the call is routed through an executor, while the return type determines the result-observation contract.** Reliable semantics additionally require timeouts, error handling, thread context management, and admission/durability aligned with business requirements.