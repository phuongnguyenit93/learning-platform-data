# thenApply() Transforms Results and thenCompose() Chains Dependent Work

> **Module:** Spring Framework – concurrency  
> **Group:** CompletableFuture Composition  
> **Goal:** Understand how to build a dependent pipeline with `CompletableFuture`: `thenApply()` transforms the **value** of a completed stage, while `thenCompose()` uses the result to **start or connect another asynchronous stage** and flattens the result. Clearly distinguish return types, callback execution timing, executors, errors, and operational limits in Spring applications.

## 1. Short Answer: map vs. flatMap

Both methods are triggered only when the preceding stage **completes normally**, and both receive that stage's value. The difference lies in **what the callback function returns** and **the type of the next future**:

- `thenApply(fn)`: the callback takes `T` and returns `U`. The result is `CompletableFuture<U>`. Use it when you already have a value and only need to transform it into a new value, such as `User -> user.name()`, `Order -> OrderDto`, `Integer -> String`.
- `thenCompose(fn)`: the callback takes `T` and returns a `CompletionStage<U>`. The result is a **chained/flattened** `CompletableFuture<U>` that completes only according to the outcome of the stage returned by the callback. Use it when the next step **depends on the result of the previous step** and the next step itself already returns an async stage, such as `userId -> fetchOrdersAsync(userId)`.

You can remember this through a comparison of data shapes:

~~~text
CompletableFuture<T>
    .thenApply(T -> U)
          => CompletableFuture<U>

CompletableFuture<T>
    .thenApply(T -> CompletableFuture<U>)
          => CompletableFuture<CompletableFuture<U>>  [NESTED]

CompletableFuture<T>
    .thenCompose(T -> CompletionStage<U>)
          => CompletableFuture<U>                     [FLATTENED]
~~~

`thenCompose` is close to `flatMap` in how it composes wrapped values; `thenApply` is close to `map`. This is an explanation by analogy, not an actual API signature identical to `Stream` or `Optional`.

## 2. What Do CompletableFuture and CompletionStage Represent?

JDK's `CompletableFuture<T>` is both a `Future<T>` (observe/wait for a result) and an implementation of `CompletionStage<T>` (register dependent processing steps).

A stage can be **incomplete**, **completed normally with a value T**, or **completed exceptionally**. Calling `thenApply`/`thenCompose` creates a new stage; it does not mutate or replace the source future object itself, nor does it guarantee that the callback runs on another thread.

Pipeline example:

~~~text
fetchUserAsync("u-17") : CompletableFuture<User>
                  |
                  v  thenApply(user -> user.id())
              CompletableFuture<String>
                  |
                  v  thenCompose(id -> fetchOrdersAsync(id))
              CompletableFuture<List<Order>>
                  |
                  v  thenApply(orders -> toSummary(orders))
              CompletableFuture<Summary>
~~~

In the diagram, the order-fetching step needs the user's `id`. Because `fetchOrdersAsync(id)` itself returns `CompletableFuture<List<Order>>`, using `thenCompose` at that step keeps the final pipeline type easy to use, rather than `CompletableFuture<CompletableFuture<List<Order>>>`.

**"Asynchronous" does not mean every callback runs asynchronously.** A future may already be complete before a callback is attached; a callback without the `Async` suffix may run immediately upon registration or on the thread completing the source stage. Waiting via `join()`/`get()` in the caller is still a blocking action if the value is not ready yet.

## 3. Type Signatures and How to Choose

In `CompletableFuture<T>`, the methods have the general forms:

~~~java
<U> CompletableFuture<U> thenApply(Function<? super T, ? extends U> fn)

<U> CompletableFuture<U> thenCompose(
    Function<? super T, ? extends CompletionStage<U>> fn)
~~~

These are **abbreviated API signatures**, not two methods to copy into a Java class. `CompletionStage<U>` is an interface: the `thenCompose` callback is not required to return the exact `CompletableFuture<U>` class, only a compatible stage.

Quick selection table:

| Callback returns | Use | Desired result type |
| --- | --- | --- |
| Single value `String`, `int`, `Dto`, `List<Order>` | `thenApply` | `CompletableFuture<U>` |
| `CompletionStage<U>` or `CompletableFuture<U>` | `thenCompose` | Flattened `CompletableFuture<U>` |
| Need to use two **independent** futures and wait for both to finish | Usually `thenCombine`/`allOf` | Parallel coordination, not dependent on the previous output |
| No need to produce a new value, only consume the result | `thenAccept` | `CompletableFuture<Void>` |
| No need for the previous stage's input, only run an action when done | `thenRun` | `CompletableFuture<Void>` |

**Do not choose based on workload size.** "Heavy processing steps should use `thenCompose`" is wrong. Choose `thenCompose` because the callback returns a *stage*, while which executor runs the work is controlled by a different mechanism.

## 4. thenApply(): Synchronous Value Transformation at the Callback Level

Given a `CompletableFuture<User>`, we can convert `User` to a DTO right after receiving the data:

~~~java
CompletableFuture<String> displayName =
    userFuture.thenApply(user -> user.name().trim().toUpperCase());
~~~

This is an **application integration snippet** assuming `userFuture` of type `CompletableFuture<User>` already exists and `User.name()` returns `String`. When the user future succeeds, the callback runs and produces a string; the new future completes with that string.

Key points:

1. `thenApply` **does not require creating a new task** on a thread pool. The mapper function may execute inline according to `CompletableFuture`'s completion policy.
2. If the source stage completes exceptionally, the normal mapping callback **does not run**; the dependent stage completes exceptionally.
3. If the mapper throws an exception, the new stage completes exceptionally rather than throwing directly to the caller thread that is registering a waiting continuation.
4. Returning `null` from a mapper is valid and the new stage completes normally with `null`; handle this when business logic does not allow null values.
5. A mapper does not make I/O asynchronous on its own. If it makes a blocking network/DB call inside, it still holds the thread running the callback until that call finishes.

**Using `thenApply` for short, pure, or lightweight transformations** is usually the convenient choice; when the callback is CPU-heavy or requires resource isolation, consider `thenApplyAsync(fn, executor)` on an explicitly provisioned and bounded executor.

## 5. thenCompose(): A Dependent Step Returning Another Stage

Suppose the system API already provides:

~~~java
CompletableFuture<User> fetchUserAsync(String userId);
CompletableFuture<List<Order>> fetchOrdersAsync(String userId);
~~~

These are **two illustrative signatures**, not a standalone program; `User` and `Order` are domain types that must be defined.

When the order-fetching step needs the user ID from the previous step:

~~~java
CompletableFuture<List<Order>> ordersFuture =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()));
~~~

Mechanism:

1. `fetchUserAsync` returns a future. The callback inside `thenCompose` **does not run** while the source future has not completed normally.
2. When the user is ready, the callback gets `user.id()` and calls `fetchOrdersAsync`, receiving **another stage**.
3. The future returned by `thenCompose` completes based on the outcome of the orders stage, not simply because the callback returned a future object.
4. The next step `.thenApply(orders -> ...)` receives `List<Order>` directly, without unwrapping another layer of future.

This is **dependent stage chaining**, not creating parallel concurrency by itself. Calling `fetchOrdersAsync` happens **after** the user stage completes; the actual asynchrony of fetching orders depends on the implementation of `fetchOrdersAsync`.

If the callback returns `null` instead of a valid `CompletionStage`, the resulting stage fails (typically with `NullPointerException`). Do not use `null` to represent "no next step"; use `CompletableFuture.completedFuture(defaultValue)` or an appropriate completed stage per your business contract.

## 6. The Nested Future Mistake When Using thenApply for Async Operations

A common mix-up:

~~~java
CompletableFuture<CompletableFuture<List<Order>>> nested =
    fetchUserAsync("u-17")
        .thenApply(user -> fetchOrdersAsync(user.id()));
~~~

The nested type is **valid Java**, but usually inconvenient:

- `nested` can complete normally as soon as the callback returns the `ordersFuture` object, **even if the orders have not finished loading yet**.
- `nested.get()` returns **another future**, not the list of orders.
- An error in the **inner future** may not be reflected as an exceptional completion of the outer future. If the code only inspects the outer future, it may wrongly conclude that the whole job succeeded.
- Downstream code needs double unwrapping or manual callback attachment, increasing complexity and the risk of missing error handling.

Fix:

~~~java
CompletableFuture<List<Order>> flat =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()));
~~~

All subsequent steps receive `List<Order>` directly; errors raised in either stage follow the exceptional completion path of the resulting chain.

**Note:** `thenCompose` does not "cancel" the inner stage or prevent it from running; it only expresses dependency and coordinates completion. Running tasks, cancel/timeout mechanisms, and downstream resources still need to be designed separately.

## 7. Standalone Java 17+ Example

The following example simultaneously demonstrates value transformation, nested futures, dependent future chaining, report generation, and error fallback. It uses only the JDK without Spring so the type and behavior differences are clear; when integrating with Spring, the source future can come from `@Async` or `AsyncTaskExecutor`.

Create **ComposeDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ComposeDemo {
    static CompletableFuture<String> findOrderAsync(
            String userId, ExecutorService pool) {
        return CompletableFuture.supplyAsync(
            () -> "order-" + userId, pool);
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<String> user =
                CompletableFuture.supplyAsync(() -> "u-17", pool);

            CompletableFuture<String> transformed =
                user.thenApply(id -> "user=" + id);

            CompletableFuture<CompletableFuture<String>> nested =
                user.thenApply(id -> findOrderAsync(id, pool));

            CompletableFuture<String> flattened =
                user.thenCompose(id -> findOrderAsync(id, pool));

            CompletableFuture<String> report =
                user.thenCompose(id -> findOrderAsync(id, pool))
                    .thenApply(order -> "summary:" +
                        order.toUpperCase(Locale.ROOT));

            System.out.println("apply = " + transformed.join());
            System.out.println("nested = " + nested.join().join());
            System.out.println("compose = " + flattened.join());
            System.out.println("chain = " + report.join());

            CompletableFuture<String> failure =
                CompletableFuture.<String>failedFuture(
                    new IllegalStateException("downstream unavailable"))
                .thenApply(String::toUpperCase);
            System.out.println("recovery = " +
                failure.exceptionally(error -> "fallback").join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run commands:

~~~bash
javac ComposeDemo.java
java ComposeDemo
~~~

**Exact program stdout**:

~~~text
apply = user=u-17
nested = order-u-17
compose = order-u-17
chain = summary:ORDER-U-17
recovery = fallback
~~~

This example has been **compiled and executed with a JDK supporting Java 17+**; the `System.out.println` lines appear in deterministic order because the caller calls `join()` on each future in the desired order, regardless of when the two workers finish their work.

Reading by type:

- `transformed`: `CompletableFuture<String>` from a single value transformation.
- `nested`: `CompletableFuture<CompletableFuture<String>>`; solely for illustration we call `nested.join().join()` on the **main thread**. Do not copy that nested blocking pattern into a callback running in a pool.
- `flattened`: direct `CompletableFuture<String>`, requiring only a single `join()` at the final boundary of the program.
- `report`: `thenCompose` fetches the order for the user, and `thenApply` turns the order into a report string.
- `failure`: the previous stage completed exceptionally, `thenApply` does not execute the mapper, and `exceptionally` returns the fallback string.

In the example, `findOrderAsync` simulates async work with `supplyAsync`, not a real HTTP client. An HTTP client with an async API can return a future without occupying a worker while waiting on the network; conversely, placing a blocking call inside `supplyAsync` still occupies a worker for the entire duration of the call.

## 8. Integrating Properly with Spring @Async

Spring `@Async` can return `CompletableFuture<T>` so the caller can continue composing stages. Key conditions:

1. Enable `@EnableAsync` in the appropriate `ApplicationContext`.
2. Call the `@Async` method **through a Spring proxy**; self-invocation `this.method()` in proxy mode normally bypasses the interceptor.
3. Configure an appropriate executor so production work does not rely on uncontrolled concurrency settings.
4. The `@Async` method returns a `CompletableFuture` completed locally from the **worker** when the method body finishes; the proxy provides the future to the caller to observe/chain subsequent steps.
5. Place dependent async steps in an injected service, and do not call `join()` inside a worker just to wait for another task on the same pool.

**Spring Framework integration** example—requires Spring context dependencies and must be loaded by an ApplicationContext, not a standalone Java file compiled with just `javac`:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfig {
    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("io-");
        return pool;
    }
}

@Service
class RemoteLookup {
    @Async("ioExecutor")
    public CompletableFuture<String> fetchUserId(String ref) {
        // Illustration: replace with an actual I/O task.
        return CompletableFuture.completedFuture("u-" + ref);
    }

    @Async("ioExecutor")
    public CompletableFuture<String> fetchOrder(String userId) {
        return CompletableFuture.completedFuture("order-" + userId);
    }
}

@Service
class SummaryService {
    private final RemoteLookup remote;

    SummaryService(RemoteLookup remote) {
        this.remote = remote;
    }

    public CompletableFuture<String> summary(String ref) {
        return remote.fetchUserId(ref)
            .thenCompose(remote::fetchOrder)
            .thenApply(order -> "summary:" + order);
    }
}
~~~

An external caller invoking `SummaryService.summary("17")` receives a `CompletableFuture<String>` whose successful value is **`summary:order-u-17`**. In this configuration, `RemoteLookup` is a **different bean** from `SummaryService`, so `remote::fetchOrder` goes through the `@Async` proxy. If changed to `this.fetchOrder(...)` within the same annotated instance, the async behavior can differ due to self-invocation.

**Do not conclude that `thenCompose` itself adds a submission to `ioExecutor`.** The submission in the second step happens because the `remote.fetchOrder` call goes through the `@Async` interceptor. `thenCompose` only connects the returned future. If `fetchOrder` is a non-async API, merely using `thenCompose` does not make it asynchronous I/O.

You can create a future directly from `AsyncTaskExecutor.submitCompletable(Callable<T>)` in Spring Framework 6.0+, or from asynchronous I/O APIs. To compose them, the stages only need compatible types; the source futures do not have to come from the same library or executor.

## 9. How Do thenApplyAsync / thenComposeAsync Differ?

Both main methods have `Async` variants:

~~~java
future.thenApply(x -> transform(x));
future.thenApplyAsync(x -> transform(x));
future.thenApplyAsync(x -> transform(x), executor);

future.thenCompose(x -> fetchAsync(x));
future.thenComposeAsync(x -> fetchAsync(x));
future.thenComposeAsync(x -> fetchAsync(x), executor);
~~~

These are **illustrative integration API snippets**; the `transform` and `fetchAsync` functions and the `future`/`executor` variables must exist in the application.

- Without the `Async` suffix: the dependent action may run on the thread completing the source future or another thread participating in completion; if the source is already complete before attaching the stage, the callback may run immediately on the registering thread.
- With the `Async` suffix, **no executor passed**: in standard JDK 17 `CompletableFuture`, it uses the default async executor; normally `ForkJoinPool.commonPool()`, unless parallelism is small or a subclass overrides the default executor. It does not default to the Spring `ThreadPoolTaskExecutor` that created the source future.
- With the `Async` suffix, **executor passed**: schedules the callback on the specified executor, allowing you to bound/isolate CPU or I/O callbacks by design. If the executor rejects the task, the dependent stage may complete exceptionally due to scheduling failure.
- Even with the `Async` suffix, **`thenApply` still only transforms a value** and **`thenCompose` still chains another stage**. The two conceptual axes are independent: *result type* and *how the callback is scheduled*.

Do not turn every stage into `thenApplyAsync` or `thenComposeAsync` by default: constantly switching pools adds overhead, complicates thread context, and creates separate load boundaries. Very lightweight string transformations usually do not need separate scheduling. CPU-heavy work or potentially blocking callbacks should be assigned to an appropriate executor.

## 10. Do Not Call join/get Inside a Callback to "Unwrap" a Future

An anti-pattern:

~~~java
CompletableFuture<List<Order>> result =
    fetchUserAsync("u-17")
        .thenApply(user ->
            fetchOrdersAsync(user.id()).join());
~~~

Although the return type is now `CompletableFuture<List<Order>>`, the callback must **synchronously wait** for the orders future via `join()`. If it runs on a worker of a small pool and orders also needs that same pool, workers can be held waiting on queued work, potentially leading to **thread starvation/deadlock**. The execution path also makes timeout and cancellation harder to manage.

Fix:

~~~java
CompletableFuture<List<Order>> result =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()));
~~~

Here the callback **returns a stage** without waiting for the inner stage's result. When orders completes, the chain completes automatically; the thread running the callback can move on to serve other tasks. The caller can still use `get()`/`join()` at a **true synchronous boundary**, such as a CLI program or test, where blocking is acceptable.

**Technical exception:** if the inner stage has already completed, `join()` may return immediately. However, business code should not rely on that as a guarantee across all runs.

## 11. Error Propagation Along the Chain and Where to Recover

If the source stage completes exceptionally, a `thenApply`/`thenCompose` attached to it **does not run its normal callback**. The dependent stage completes exceptionally; the error may be wrapped in `CompletionException` when calling `join()`, or `ExecutionException` when calling `get()`.

Example:

~~~java
CompletableFuture<String> safeReport =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()))
        .thenApply(orders -> renderReport(orders))
        .exceptionally(error -> "report unavailable");
~~~

This is an **illustrative integration snippet**. `exceptionally` returns a replacement value, meaning the new chain can finish **successfully** with `"report unavailable"`. Placing a catch-all fallback at the end of the chain like this can swallow programming bugs in `renderReport`, downstream errors, and cancellation. Classify errors, log correlation IDs, attach metrics, and only fall back on errors that business logic actually permits.

Distinguishing the tools:

| API | When the callback runs | Result |
| --- | --- | --- |
| `thenApply` | Source completes normally | Produces a new value; mapper error makes the new stage exceptional |
| `thenCompose` | Source completes normally | Runs dependent step returning a stage; result follows that stage |
| `exceptionally(fn)` | Source completes exceptionally | Returns a fallback value to **recover** the new stage |
| `handle((value,error) -> ...)` | Source succeeds or fails | Turns either outcome into a single result decided by the handler |
| `whenComplete((value,error) -> ...)` | Source succeeds or fails | Suitable for recording side effects/logging; typically preserves the original outcome unless the callback itself throws |

If the `thenCompose` callback throws an exception **before** returning a stage, the outer future fails. If the callback returns a stage and that stage fails, the outer future also fails with the outcome of the chained stage. This is a major benefit of flattening: consumers of the chain only need to observe a single result future.

Do not assume `Future.get()` returns `null` on error; it throws an exception. If you use `exceptionally` to turn an error into a valid result, define the business error state explicitly so you do not accidentally mark a failed order as successful.

## 12. Timeouts and Cancellation Do Not Automatically Stop Every Inner Task

`CompletableFuture` methods such as `orTimeout` and `completeOnTimeout` support time policies:

~~~java
CompletableFuture<Summary> withDeadline =
    reportFuture.orTimeout(2, TimeUnit.SECONDS);

CompletableFuture<Summary> withFallback =
    reportFuture.completeOnTimeout(defaultSummary, 2, TimeUnit.SECONDS);
~~~

This is an **illustrative API snippet** (requires importing `TimeUnit` and domain variables). Both timing methods can **complete the very future they are called on** when the deadline arrives. If both methods are called on the *same instance*, they can interact with each other; the example separates them for illustration, not as two independent timeouts applied to one future.

- `orTimeout`: completes the future with `TimeoutException` if not completed by the deadline.
- `completeOnTimeout`: completes the future with a fallback value if not finished by the deadline.
- A future's timeout **does not guarantee** automatic cancellation of an HTTP request, JDBC query, downstream job, or already-started thread. You need timeouts/cancellation at the actual client, transaction, and I/O boundaries.
- `cancel(true)` on JDK `CompletableFuture` does not have a mechanism to interrupt the underlying computation like a worker-bound `FutureTask`; it is a form of exceptional completion. Stages that have already started may continue causing side effects.
- Cancellation on one stage does not mean propagation across the entire dependent chain is built in. Stopping tasks, reclaiming resources, and avoiding duplicate data creation must be designed for the actual system.

A dependent pipeline may time out while an inner stage still finishes processing afterward. Therefore use idempotency keys, clear terminal states, and metrics to handle late-arriving results.

## 13. Performance, Thread Pools, and Context in Spring

`thenCompose` eliminates blocking waits inside callbacks, **but does not give the system more capacity**. When an application uses Spring `@Async` and multiple tasks share a `ThreadPoolTaskExecutor`:

1. Choose `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy, and shutdown settings appropriately. An overly long queue can mask overload; a bounded queue requires handling rejections.
2. Record metrics for queue length, active workers, wait time, task duration, failures, and timeouts. Creating a future does not mean the task was definitely accepted or executed successfully.
3. CPU-heavy callbacks should run on a dedicated or controlled executor; avoid turning `commonPool` into a place for high-volume blocking I/O.
4. `ThreadLocal`, MDC, security, and request contexts are not automatically guaranteed to propagate to the thread completing the future or continuation. When context propagation is needed, use a `TaskDecorator` or appropriate adapter/context mechanism and clean up scoped data.
5. In imperative Spring applications, transactions are bound to the current thread. `thenCompose` **does not propagate the caller's transaction to another worker**; each DB write step needs properly scoped transactions and must not assume the previous stage's work has committed unless guaranteed by contract.
6. A singleton bean called concurrently by multiple stages must be thread-safe; `thenApply` does not protect a mutable `HashMap` or shared counter.
7. If a task must survive a JVM restart or run at least once, `CompletableFuture` is only **in-memory** state, not a durable queue. Use a job store, outbox/idempotency, and appropriate retry/backpressure.

An important note on overload: when the executor submitting a task for `@Async` rejects it, calling `remote.fetchOrder(id)` can throw `TaskRejectedException`. If this happens inside a `thenCompose` callback, the chain completes exceptionally. In that situation do not hot-retry or immediately resubmit to a saturated pool; use a bounded retry policy with backoff and jitter when business rules allow.

## 14. Sequential Dependency or Independent Parallelism?

Do not use `thenCompose` for two requests that are **truly independent** just because both are asynchronous. Example of two data sources called independently:

~~~java
CompletableFuture<Customer> customer = fetchCustomerAsync(id);
CompletableFuture<Discount> discount = fetchDiscountAsync(id);

CompletableFuture<Pricing> pricing =
    customer.thenCombine(discount,
        (c, d) -> calculatePricing(c, d));
~~~

This is an **illustrative integration snippet**, assuming APIs and types `Customer`, `Discount`, `Pricing` exist. The two requests can already run in parallel because both are initiated before combining; `thenCombine` waits for both to complete normally to calculate pricing.

Compare when step two **genuinely needs the result of step one**:

~~~java
CompletableFuture<Pricing> pricing =
    fetchCustomerAsync(id)
        .thenCompose(customer ->
            fetchDiscountAsync(customer.tier())
                .thenApply(discount ->
                    calculatePricing(customer, discount)));
~~~

In the second case, the discount step depends on `customer.tier()`, so it cannot legitimately start before the customer is available. `thenCompose` chains the second request, and the inner `thenApply` uses both the captured customer and the discount to produce `Pricing`.

Making this distinction helps design better latency:

- **Dependency:** stage B needs A's output -> `thenCompose`.
- **Independent:** A and B can be started right away -> `thenCombine`/`allOf`.
- **Synchronous mapping:** converting a result into a new format/DTO -> `thenApply`.
- **Side effect with no return value:** `thenAccept`/`thenRun` are better than writing a mapper that always returns a dummy value.

## 15. Common Mistakes and How to Fix Them

| Misconception / Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Using `thenApply` for a callback returning `CompletableFuture<U>` when expecting `U` | Creates nested futures | Use `thenCompose` |
| Using `thenApply(x -> fetchAsync(x).join())` | Blocks the callback thread, possible starvation | Use `thenCompose(this::fetchAsync)` |
| Thinking `thenCompose` creates a new thread by default | Wrong assumptions about scheduling and resources | Distinguish `thenCompose` from `thenComposeAsync`/executor |
| Always using `thenApplyAsync` without passing an executor in Spring apps | Callback may run in `commonPool`, different from Spring's pool | Supply an explicit executor when control is needed |
| Ignoring the resulting future and watching only the source future | Misses errors occurring in dependent stages | Observe the **final future** of the pipeline |
| Calling `get()` right after every stage | Accidentally serializes blocking in the caller | Chain stages and wait only at a real boundary |
| Adding a broad `exceptionally` and treating fallback as business success | Swallows data errors or programming bugs | Recover only allowed errors; separate status/metrics |
| Believing `orTimeout` has stopped remote I/O | Tasks may keep running after timeout | Set client I/O timeouts and separate cancellation/compensation |
| Calling `@Async` via `this.method()` | Bypasses proxy; method runs synchronously | Call bean via Spring proxy / proper service structure |
| Believing `thenCompose` transfers transaction, MDC, or security context | Context depends on thread and propagation mechanisms | Propagate context explicitly; use separate transactions |
| Returning `null` from a `thenCompose` callback | Completion failure instead of skipping the stage | Return a valid `CompletionStage` |
| Letting many blocking tasks share an undersized pool | Queue buildup, possible starvation/rejection | Separate I/O and CPU pools, measure load, bound queues |

## 16. Testing to Prove the Pipeline Works Correctly

A good test suite for these two methods should not only assert the final value, but also prove structure and error paths:

1. **Transform:** create `CompletableFuture.completedFuture(5)`, call `.thenApply(n -> n * 2)`; verify `join() == 10`.
2. **Compose:** have the mapper return an incomplete `CompletableFuture<String>`; verify the outer stage after `thenCompose` is **not done yet**, then complete the inner one and assert the result.
3. **Nested type:** declare a variable of type `CompletableFuture<CompletableFuture<String>>` with `thenApply`; the compiler confirms the exact nested future layer.
4. **Source failure:** `failedFuture(new IllegalArgumentException(...))` must prevent the normal mapper from running; the dependent stage fails.
5. **Inner stage failure:** the `thenCompose` callback returns a failing stage; the outer stage must also fail and the error must be observable.
6. **Executor:** use a thread-name prefix or custom executor to verify `thenApplyAsync(fn, executor)` uses the specified executor; do not assert a fixed thread name when the API does not guarantee one.
7. **Spring proxy:** call `@Async` through an injected bean; do not use `new Service()` or self-invocation in tests expecting async execution.
8. **Concurrency:** use `CountDownLatch` or a test scheduler to avoid flaky tests relying on `Thread.sleep` and non-deterministic execution order.
9. **Timeout/cancellation:** simulate a long-running stage with a side effect; verify a future timeout does not automatically roll back external results.
10. **Saturation:** fill an executor with a bounded queue and verify rejection is reflected on the exceptional completion path rather than swallowed.

An example that can test flattening logic on its own without creating threads:

~~~java
CompletableFuture<String> inner = new CompletableFuture<>();
CompletableFuture<String> flat =
    CompletableFuture.completedFuture("id")
        .thenCompose(ignored -> inner);

System.out.println(flat.isDone()); // false
inner.complete("ready");
System.out.println(flat.join());   // ready
~~~

This is a **code snippet to paste inside a Java method** (requires importing `CompletableFuture`), not a standalone class. The outputs of the two `println` calls are `false` and `ready` respectively because `inner` is not yet complete before `inner.complete` is called.

## 17. Code Review Checklist

- I know whether the callback returns a **value U** or a **CompletionStage<U>** before choosing `thenApply` or `thenCompose`.
- I am not accidentally creating `CompletableFuture<CompletableFuture<U>>` when I want a flat result.
- I am not using `join()`/`get()` inside a continuation to force an asynchronous task to be synchronous.
- I know a callback without the `Async` suffix may run inline or on the thread completing the source stage.
- I use `thenApplyAsync/thenComposeAsync` and an explicit executor when there is a reason to control the thread pool.
- I am not confusing `thenCompose` with running independent tasks in parallel.
- I handle errors from both the source stage and the chained stage, and place recovery at the right business boundary.
- I have policies for timeout, cancellation, backpressure, and retry, and do not mistake a timeout for stopping side effects.
- I verified that Spring `@Async` is invoked through a proxy, and transactions/contexts are not assumed to propagate.
- I know who owns the **final future** and is responsible for observing the completion status of the entire pipeline.

**Conclusion:** Use `thenApply()` when you only need to transform an **existing value**; use `thenCompose()` when the next step depends on that value and returns **an asynchronous stage**, giving you a **flat** future to track the entire outcome. In Spring, proper design also requires choosing the executor, controlling thread counts, errors, timeouts, and proxy/transaction boundaries.

## Official References

- Java SE 17: [CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — semantics of `thenApply`, `thenCompose`, async variants, completion, exceptions, and cancellation.
- Java SE 17: [CompletionStage Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html) — dependent pipelines, callback types, and exceptional completion rules.
- Spring Framework: [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — `@EnableAsync`, `@Async`, executor selection, and `CompletableFuture` return types.
- Spring Framework: [AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html) — `submitCompletable` and submitting tasks to an executor via the Spring abstraction.
- Spring Framework: [@Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html) — signature, qualifier, and constraints when using Spring proxies.
