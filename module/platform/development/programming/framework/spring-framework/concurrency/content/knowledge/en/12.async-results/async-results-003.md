# `CompletableFuture` Enables Composing Processing Steps

**Module:** Spring Framework - concurrency  
**Group:** Asynchronous results  
**Goal:** Learn how to model a multi-step asynchronous workflow using `CompletableFuture<T>`/`CompletionStage<T>`, properly choose `thenApply`, `thenCompose`, `thenCombine`, `allOf`, and error-handling branches, while understanding executor boundaries, timeouts, and Spring `@Async` integration.

## 1. From a Single Future to a Workflow

In a Spring application, generating a price quote may require:

1. Fetching the product price.
2. Calculating tax from the price — **dependent on step 1**.
3. Fetching the shipping fee — **independent of tax calculation**.
4. Combining the taxed price and shipping fee into the grand total.
5. Based on the grand total, calling the inventory reservation service — **dependent on step 4 and also returning a future**.
6. Independently fetching the customer tier; only when both reservation and customer tier complete is the result constructed.
7. If any step fails or times out, propagating the error, applying an appropriately scoped fallback, or rejecting according to the business contract.

Written in traditional blocking style:

```java
int price = priceFuture.get();          // Wait for price.
int shipping = shippingFuture.get();    // Wait for shipping fee.
String reservation = reserve(total).get(); // Wait for next task.
```

This is an **illustrative snippet**, lacking variables `priceFuture`, `shippingFuture`, `total`, and `reserve` to compile standalone. Each `get()` can block the current thread, and fetching results step-by-step makes it easy for authors to introduce unnecessary wait points.

With `CompletableFuture`, we describe **dependency relationships** between results:

```text
getPrice() ------- thenApply(calc tax) ----+
                                           +-- thenCombine(total) -- thenCompose(reserve) --+
getShipping() -----------------------------+                                                |
                                                                                            +-- allOf --> result
getCustomerTier() --------------------------------------------------------------------------+
```

Each arrow is a **stage** (a dependent step). Downstream stages are triggered by the completion condition of upstream stages, instead of forcing the thread building the pipeline to wait at every step. **Asynchronous composition does not mean every piece of code runs on a different thread**; the executing thread depends on the executor and how `Async`-suffixed methods are used.

## 2. Nature of `CompletableFuture`

`java.util.concurrent.CompletableFuture<T>` (available since Java 8; works well in Java 17+) both:

- Implements `Future<T>`: represents a result retrievable via `get()`, trackable with `isDone()` and `cancel()`.
- Implements `CompletionStage<T>`: describes **chaining, combining, branching, and error-handling** operations once a result becomes available.
- Allows manual completion via `complete(value)` or `completeExceptionally(error)`; commonly used when adapting callback-based APIs into the Future model.

A future can be in an **incomplete** state, **completed normally** with a value of type `T`, or **completed exceptionally**. One of the completion operations wins the race; a normally completed result cannot be overwritten by calling `complete` again.

```java
CompletableFuture<Integer> result = new CompletableFuture<>();

boolean first = result.complete(42);   // true: first completion.
boolean second = result.complete(99);  // false: already completed.
System.out.println(result.join());     // 42.
```

This is valid Java 17 code when placed inside a method and importing `java.util.concurrent.CompletableFuture`. `join()` **also waits** if the future is not finished yet; the name `join` does not make waiting non-blocking.

### `completedFuture`, `failedFuture`, `supplyAsync`, and `runAsync`

| Creation method | Outcome |
| --- | --- |
| `CompletableFuture.completedFuture(42)` | Already completed successfully with `42`; creates no new task |
| `CompletableFuture.failedFuture(error)` | Already completed exceptionally; useful in tests/error paths |
| `CompletableFuture.supplyAsync(supplier, executor)` | Submits a **value-returning** computation to the specified executor |
| `CompletableFuture.runAsync(runnable, executor)` | Submits a `void` task, returns `CompletableFuture<Void>` |
| `new CompletableFuture<>()` | Incomplete future; another party must call `complete`/`completeExceptionally` or equivalent |

Merely creating `new CompletableFuture<>()` does not make a task run on its own. Merely calling `completedFuture` does not make a running method asynchronous.

## 3. Choosing Combinators: Single Source, Dependent Source, Two Independent Sources

| Scenario | API | Input → output | Waits for what condition? |
| --- | --- | --- | --- |
| Transform an already available result | `thenApply(fn)` | `T -> U` | Source future completes normally |
| Perform side work returning no data | `thenAccept(consumer)` | `T -> Void` | Source future completes normally |
| Run a next step without using the value | `thenRun(runnable)` | `T -> Void` | Source future completes normally |
| Next step **itself returns a CompletionStage** | `thenCompose(fn)` | `T -> CompletionStage<U>`, flattened result `U` | Source finishes, then returned stage also finishes |
| Combine results of **two independent futures** | `thenCombine(other, fn)` | `T + U -> V` | **Both** complete normally |
| Action using two results | `thenAcceptBoth(other, action)` | `T + U -> Void` | Both complete normally |
| Wait for **all** of a list of futures | `CompletableFuture.allOf(...)` | `... -> Void` | All complete |
| Take the **first** completed future | `CompletableFuture.anyOf(...)` | `... -> Object` | One future completes, **including exceptionally** |
| Handle success/error to change result | `handle((value, error) -> ...)` | `T or error -> U` | Source completes in any way |
| Recover only on error | `exceptionally(error -> fallback)` | Error `T -> T` | Source completes exceptionally |
| Observe success/error | `whenComplete((value, error) -> ...)` | Usually preserves original outcome | Source completes in any way |

**Remember:** `thenApply` transforms a **value**; `thenCompose` chains **another asynchronous task**; `thenCombine` merges **two independent tasks**. These three methods solve three different dependency shapes.

## 4. `thenApply`: Transforming a Single Step's Result

Suppose the base price is 200 and tax is calculated at 10%:

```java
CompletableFuture<Integer> price =
        CompletableFuture.completedFuture(200);

CompletableFuture<Integer> priceWithTax =
        price.thenApply(p -> p + p / 10);

System.out.println(priceWithTax.join()); // 220
```

`thenApply` accepts a function `T -> U`; the result is placed in a **new future**. It does **not** mutate `price`. If the source completes exceptionally, the `thenApply` lambda **does not run on the success path**; the downstream stage becomes exceptional unless an appropriate recovery mechanism exists.

Use `thenApply` for **lightweight and fast** synchronous transformations, such as DTO mapping, small data normalization, or low-CPU calculations. If the lambda must wait on DB/HTTP or perform heavy CPU work, avoid accidentally running it on another task's completion thread. When you need to explicitly choose a pool for the transformation, use `thenApplyAsync(fn, executor)` with a properly bounded executor.

## 5. `thenCompose`: Chaining a New Task and Flattening Nested Futures

This is the most important distinction when learning multi-step composition.

Suppose after knowing the grand total, we must call another service returning `CompletableFuture<String>` containing a reservation code:

```java
CompletableFuture<Integer> total =
        CompletableFuture.completedFuture(245);

CompletableFuture<String> reservation =
        total.thenCompose(amount ->
                CompletableFuture.supplyAsync(
                        () -> "RES-" + amount,
                        ioExecutor));
```

The example above is an **illustrative snippet**, requiring an `ioExecutor` variable of type `Executor` and `CompletableFuture` import. When `total` produces a value, the function returns another stage. `thenCompose` returns a `CompletableFuture<String>` completed according to the inner stage.

If written with `thenApply`, the result type becomes a **nested future**:

```java
CompletableFuture<CompletableFuture<String>> nested =
        total.thenApply(amount ->
                CompletableFuture.supplyAsync(
                        () -> "RES-" + amount,
                        ioExecutor));
```

Extra waiting/unwrapping is needed to get the real value. Therefore, when the lambda **returns a future**, think of `thenCompose` by default instead of `thenApply`.

Analogous comparison:

```text
thenApply(fn):    Future<T> + (T -> U)            -> Future<U>
thenCompose(fn):  Future<T> + (T -> Future<U>)     -> Future<U>
```

Do not stuff `join()` inside a lambda to manually "flatten":

```java
// Avoid: blocking inside a continuation easily causes stalls/deadlocks.
total.thenApply(amount -> reserveAsync(amount).join());
```

The illustrative snippet above assumes `reserveAsync(amount)` exists. If it schedules a task onto the **same pool with a small worker count** and the continuation is occupying a worker while waiting, starvation or deadlock can occur. Use `thenCompose(amount -> reserveAsync(amount))` to express the dependency without **holding a thread waiting**.

### How Does `thenComposeAsync` Differ from `thenCompose`?

`thenCompose` runs the **function that creates the next stage** under non-async completion rules; `thenComposeAsync(fn, executor)` explicitly dispatches running that function to the executor. However, **this executor does not automatically dictate where every task inside the future returned by `fn` runs**: the inner future has its own origin, network client, executor, and rules. Distinguish "running the stage-chaining callback" from "running the inner business task."

## 6. `thenCombine`: Combining Two Independent Results

Taxed price and shipping fee can be fetched concurrently, then combined once both finish:

```java
CompletableFuture<Integer> priceWithTax =
        CompletableFuture.supplyAsync(() -> 220, executor);

CompletableFuture<Integer> shipping =
        CompletableFuture.supplyAsync(() -> 25, executor);

CompletableFuture<Integer> grandTotal =
        priceWithTax.thenCombine(shipping, Integer::sum);

// Neither stage calls get()/join() to wait for the other.
System.out.println(grandTotal.join()); // 245
```

The snippet above requires an `executor` variable of type `Executor` in a real program. `thenCombine` only runs the function when **both sources complete normally**. If one source fails, the combined future also fails; it does not silently substitute `0` for the failed source.

Structural difference:

- **Sequential dependency:** step B needs A's value to know what to do → `A.thenCompose(a -> B(a))`.
- **Independent:** A and B can be launched upfront, only combining results afterward → `A.thenCombine(B, combiner)`.
- **Do not write** `A.thenCompose(a -> B())` if B does not actually depend on A: that unnecessarily delays starting B.

If two computations produce the same result type and whichever arrives first is preferred, `applyToEither` can be useful; it triggers when one source **completes normally** as required. Do not confuse it with `anyOf`, because `anyOf` can complete **exceptionally** as soon as the first source fails.

## 7. `allOf`: Waiting for Many Branches; `anyOf`: Taking the First Result

### `CompletableFuture.allOf`

```java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("A");
CompletableFuture<String> b =
        CompletableFuture.completedFuture("B");
CompletableFuture<String> c =
        CompletableFuture.completedFuture("C");

CompletableFuture<String> summary =
        CompletableFuture.allOf(a, b, c)
                .thenApply(ignored -> a.join() + b.join() + c.join());

System.out.println(summary.join()); // ABC
```

`allOf` returns `CompletableFuture<Void>`, **not a list of results**. Only after `allOf` completes normally does calling `a.join()`, `b.join()`, `c.join()` inside the continuation above require no extra waiting; they are already done. If one component fails, `allOf` completes exceptionally; the success continuation will not run. To aggregate both **successes and errors of each source**, transform each branch into a status-bearing result (`handle`) before `allOf`.

Example aggregating in **input order** (independent of execution order):

```java
List<CompletableFuture<String>> futures = List.of(a, b, c);

CompletableFuture<List<String>> values =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture[0]))
                .thenApply(ignored ->
                        futures.stream()
                                .map(CompletableFuture::join)
                                .toList());
```

The snippet above requires importing `java.util.List` and `java.util.concurrent.CompletableFuture`; it is code suitable for placing inside a method. When any future fails, all of `values` fails; it does not ignore failed sources by default.

### `CompletableFuture.anyOf`

```java
CompletableFuture<String> fast =
        CompletableFuture.completedFuture("cache");
CompletableFuture<String> slow =
        new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fast, slow);

System.out.println(first.join()); // cache
```

`anyOf` completes according to the **first future to complete**, whether normally or exceptionally, and returns `Object` because inputs can have different types. In this example `fast` is already completed beforehand, so the result is deterministic. With two genuinely racing sources, you cannot predict the winner without controlling completion timing.

**Warning:** "having one result" does not mean the remaining tasks automatically stop or get cancelled. For HTTP calls to two providers, realistic timeout/cancel/resilience policies are needed if you do not want to keep consuming resources.

### Do Not Treat `allOf` as Magically "Running Everything in Parallel"

`allOf` only **waits for** existing futures. Parallelism depends on **how each future is started** and executor resources. If you create all of them with `completedFuture`, no I/O happens. If each future calls a synchronous API on the same single-thread pool, they can still run sequentially despite using `allOf`.

## 8. `thenApply` and `Async`-Suffixed Methods: Which Thread Runs?

Methods like `thenApply`, `thenCompose`, `thenCombine`, and `whenComplete` **without the `Async` suffix** may run the callback on the thread completing the source future, or another thread performing the completion operation. If the source is already completed when registering the callback, execution may happen immediately on the registering thread.

The `Async`-suffixed variants:

- `thenApplyAsync(fn)`, `thenComposeAsync(fn)` without passing an executor: with standard `CompletableFuture`, defaults to the JDK's `ForkJoinPool.commonPool()` (with fallback rules when the common pool does not support sufficient parallelism).
- `thenApplyAsync(fn, executor)` and `thenComposeAsync(fn, executor)`: dispatches the callback to the **specified executor**, providing control over threads/queues/rejection.
- `CompletableFuture.supplyAsync(supplier, executor)`: explicitly runs the supplier in the chosen pool.
- **Declaring `@Async` on a Spring method does not make parameterless `thenApplyAsync()` calls elsewhere automatically switch to the Spring executor.** Pass the executor explicitly whenever you want the same pool.

Lightweight mapping example:

```java
CompletableFuture<OrderDto> dto =
        orderFuture.thenApply(OrderDto::from);
```

CPU-heavy mapping isolated to a pool example:

```java
CompletableFuture<byte[]> compressed =
        fileFuture.thenApplyAsync(
                bytes -> compress(bytes),
                cpuExecutor);
```

Both snippets are **in-application illustrations**: they require `OrderDto`, `orderFuture`, `fileFuture`, `compress`, and `cpuExecutor` defined by the project.

**Do not assume `thenApplyAsync` is faster by default**: it adds another scheduling/queueing step and can cause rejection. Choose an async boundary when you genuinely need to decouple work from the completion thread, protect a resource, or segregate workload types.

## 9. Error Patterns and Controlled Recovery

When a stage completes exceptionally, downstream "success" stages depending on it (such as `thenApply`, `thenCompose`, `thenCombine`) normally also complete exceptionally; success callbacks do not run. Errors must be handled as part **of the pipeline**, rather than expecting the caller to directly catch exceptions from a worker.

| API | When is it called? | What is it used for? | Downstream stage value |
| --- | --- | --- | --- |
| `exceptionally(error -> fallback)` | Only on error | Recover with a value of the same type `T` | Normal if fallback does not throw |
| `handle((value, error) -> newValue)` | Both success and error | Transform both branches into a result `U` | Depends on handler function |
| `whenComplete((value, error) -> log(...))` | Both success and error | Observe for logs/metrics/cleanup | Usually preserves original success/error; callback can also throw |
| `exceptionallyCompose(error -> otherFuture)` (Java 12+) | On error | Recover with a **new asynchronous stage** | Follows fallback stage |
| `completeExceptionally(error)` | Called explicitly | Marks **current future** as failed if not yet completed | Boolean indicating whether it won the race |

Fallback example for an acceptable error:

```java
CompletableFuture<String> displayName =
        lookupNameAsync(userId)
                .exceptionally(error -> "Guest");

```

This snippet is not standalone: `lookupNameAsync(userId)` and `userId` belong to the application. **Only use a fallback when it does not break business invariants.** A default display name may be fine, but you must not silently substitute `0` for a payment amount if the error is failing to fetch the real price.

Example needing an asynchronous fallback:

```java
CompletableFuture<Profile> profile =
        fetchFromPrimary(userId)
                .exceptionallyCompose(error ->
                        fetchFromReplica(userId));
```

`Profile`, `fetchFromPrimary`, and `fetchFromReplica` must be defined in the application; the example only illustrates the flow. `exceptionallyCompose` avoids nested fallback stages and avoids blocking with `join()`.

### `handle` Can Accidentally Swallow Errors

```java
CompletableFuture<Integer> parsed =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("invalid"))
                .handle((value, error) ->
                        error == null ? value : -1);
```

`parsed` completes normally with `-1`: the original error was **converted into data**. This is an explicit contract decision, not a harmless side effect. If no valid fallback exists, record the error and **preserve** the error state.

### `whenComplete` Is for Observation, Not Value Replacement

```java
CompletableFuture<String> result =
        workFuture.whenComplete((value, error) -> {
            if (error != null) {
                metrics.recordFailure(error);
            } else {
                metrics.recordSuccess();
            }
        });
```

This is an illustrative snippet (`workFuture`, `metrics` provided by the application). The callback may be invoked on an unpredictable thread when using the non-Async version. The callback must also handle its own exceptions; if the callback throws when the source succeeded, the resulting stage can become exceptional. Do not put long-running blocking work into a shared observation callback.

## 10. `get()` and `join()`: Where Does Blocking Actually Happen?

Both `get()` and `join()` **can block the calling thread** until the future completes.

- `get()` has `InterruptedException`, `ExecutionException`; `get(timeout, unit)` also has `TimeoutException` when the waiting thread exceeds the limit. Suitable at boundaries needing deliberate checked exception/interrupt handling.
- `join()` returns the value or throws unchecked `CompletionException` (or `CancellationException` when cancelled); convenient when stages have already completed or when handling at an outer boundary.
- `getNow(fallback)` does not wait, returning `fallback` if not yet finished; if completed exceptionally it can still throw.
- `isDone()` does not mean success: it could be normal completion, error, or cancellation.
- `get(timeout)` **bounds the caller's wait time**; it does not necessarily complete exceptionally or stop the underlying future.

Do not call `join` in a controller right after building a pipeline and claim the endpoint is non-blocking:

```java
// Can block the Servlet thread until processing completes.
String value = someFuture.join();
```

In Spring MVC, you can return `CompletableFuture<T>` or `CompletionStage<T>` via the supported async return type mechanism, or use `DeferredResult`/`Callable` appropriately, instead of blocking the request thread. However, an endpoint returning a future may still **keep the HTTP response open** waiting for the result. If you need to return `202 Accepted` immediately and process later, you must create a separate job ID/status contract and durable persistence capability.

## 11. Timeouts, Cancellation, and the Responsibility to Stop Work

Java 9+ provides:

```java
CompletableFuture<String> timed =
        remoteCallAsync()
                .orTimeout(2, java.util.concurrent.TimeUnit.SECONDS);
```

This is an **illustrative snippet**; it requires `remoteCallAsync()` returning `CompletableFuture<String>`. `orTimeout` causes **the CompletableFuture receiving the call itself** to complete exceptionally with `TimeoutException` if overdue. It **does not automatically cancel** the underlying network call, DB query, or running task. Queued continuations may also still execute depending on design. To return a default value:

```java
CompletableFuture<String> withFallback =
        remoteCallAsync()
                .completeOnTimeout(
                        "temporarily-unavailable",
                        2, java.util.concurrent.TimeUnit.SECONDS);
```

`completeOnTimeout` also acts on **the future the method is called on**, rather than "creating an independent clone to time out." If a future is shared among multiple consumers, applying a timeout can alter the result seen by other consumers. Consider creating an independent dependent stage and applying the timeout to that stage when you need to isolate timeout policies (and clearly understand error propagation).

`cancel(true)` on a `CompletableFuture` is treated as **exceptional completion with `CancellationException`**; the `mayInterruptIfRunning` parameter does not guarantee interrupting the thread executing the supplier. To cancel real work, integrate proper cancellation APIs of the HTTP/JDBC client, cooperative cancellation/interrupts or tokens, along with resource cleanup rules.

Timeouts and cancellation should derive from the request's **overall deadline**, not each step picking a large timeout and adding them up. For example, a request with a 2-second end-to-end budget cannot give three sequential calls 2 seconds each and still meet its SLA.

## 12. Standalone Java 17 Program: Sequential + Parallel + Error Pipeline

The following example compiles with **JDK 17 or higher**, without needing Spring. It demonstrates:

- `supplyAsync` with an explicitly passed `ExecutorService`.
- `thenApply` calculating tax after obtaining the price.
- `thenCombine` merging price with **independent** shipping fee.
- `thenCompose` calling a future-returning reservation step without creating nested futures.
- `allOf` waiting for both reservation and customer tier results.
- `exceptionally`, `handle`, and `whenComplete` under different contracts.
- Responsible executor `shutdown`, without assuming worker order.

Save verbatim as **`CompletableFutureCompositionDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureCompositionDemo {

    private static CompletableFuture<Integer> fetchBasePrice(Executor executor) {
        return CompletableFuture.supplyAsync(() -> 200, executor);
    }

    private static CompletableFuture<Integer> fetchShipping(Executor executor) {
        return CompletableFuture.supplyAsync(() -> 25, executor);
    }

    private static CompletableFuture<String> fetchCustomerTier(Executor executor) {
        return CompletableFuture.supplyAsync(() -> "GOLD", executor);
    }

    private static CompletableFuture<String> reserveInventory(
            int total, Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> "RES-" + total, executor);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(4);
        try {
            CompletableFuture<Integer> withTax =
                    fetchBasePrice(executor)
                            .thenApply(price -> price + price / 10);

            // Started independently of withTax.
            CompletableFuture<Integer> shipping =
                    fetchShipping(executor);

            CompletableFuture<Integer> total =
                    withTax.thenCombine(shipping, Integer::sum);

            // Callback creates another future: use thenCompose.
            CompletableFuture<String> reservation =
                    total.thenCompose(amount ->
                            reserveInventory(amount, executor));

            CompletableFuture<String> tier =
                    fetchCustomerTier(executor);

            CompletableFuture<String> report =
                    CompletableFuture.allOf(reservation, tier)
                            .thenApply(ignored ->
                                    reservation.join() + "/" + tier.join());

            System.out.println("total=" + total.join());
            System.out.println("reservation=" + reservation.join());
            System.out.println("report=" + report.join());

            CompletableFuture<String> recovered =
                    CompletableFuture.<String>failedFuture(
                            new IllegalStateException("service down"))
                            .exceptionally(error -> "fallback");

            System.out.println("recovered=" + recovered.join());

            CompletableFuture<String> handled =
                    CompletableFuture.<String>failedFuture(
                            new IllegalArgumentException("invalid"))
                            .handle((value, error) ->
                                    error == null ? value : "invalid-input");

            System.out.println("handled=" + handled.join());

            AtomicInteger observedCount = new AtomicInteger();
            CompletableFuture<String> observed =
                    CompletableFuture.completedFuture("ok")
                            .whenComplete((value, error) ->
                                    observedCount.incrementAndGet())
                            .thenApply(String::toUpperCase);

            System.out.println("observed=" + observed.join());
            System.out.println("observedCount=" + observedCount.get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
javac CompletableFutureCompositionDemo.java
java CompletableFutureCompositionDemo
```

**Stdout printed by the program upon normal termination:**

```text
total=245
reservation=RES-245
report=RES-245/GOLD
recovered=fallback
handled=invalid-input
observed=OK
observedCount=1
```

Explanation:

1. `fetchBasePrice` returns `200`; `thenApply` adds 10% tax to yield `220`.
2. Independent shipping fee is `25`; `thenCombine` yields `245`.
3. `thenCompose` submits a new reservation step with total `245`, returning `RES-245` without nested futures.
4. `allOf` requires both reservation and `GOLD` tier to complete; `report` combines them in the lambda's order, regardless of which worker finishes first.
5. The two failed futures are turned into illustrative fallback values by `exceptionally`/`handle`. In billing logic, whether a fallback is valid must be evaluated separately.
6. `whenComplete` increments the counter exactly once and lets `"ok"` pass through `thenApply` to become `"OK"`.

Because the program only prints on the `main` thread **after waiting on the corresponding futures**, line order and content are deterministic; the actual execution order of the 4 workers is non-deterministic. `Executors.newFixedThreadPool` has a memory-unbounded queue and is only used to simplify the example; real services should use an executor with an appropriately bounded queue/admission policy.

**Key learning point:** the pipeline accurately expresses task *dependencies*, yet at the end of a CLI program `join()` is still needed to print results after completion. This is completely different from calling `join()` inside a continuation or in a request thread that must stay responsive.

## 13. Integrating with Spring `@Async` at the Right Boundary

A Spring service can return `CompletableFuture<T>` from an `@Async` method. Spring dispatches the invocation through the configured executor, and then the caller composes the returned futures using JDK APIs.

In a **Spring Boot 3.x, Java 17+** project with `spring-boot-starter-web` or appropriate Spring Context, the three files below illustrate how to wire the components. These are **classes belonging to a Spring project**, not a standalone plain `javac` program; the runnable JDK program is in section 12.

### 13.1. Bounded Executor and Enabling `@Async`

File `src/main/java/com/example/quote/AsyncConfig.java`:

```java
package com.example.quote;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean("quoteIoExecutor")
    public ThreadPoolTaskExecutor quoteIoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("quote-io-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

This is an **illustrative configuration**; the values 4/8/32 must be measured against real load and DB/HTTP connection limits. Since the executor is a Spring bean, the container manages the `ThreadPoolTaskExecutor` lifecycle. Simply adding `@EnableAsync` does not guarantee methods are invoked properly through the Spring proxy.

### 13.2. Two Independent Result Sources

File `src/main/java/com/example/quote/QuoteDataService.java`:

```java
package com.example.quote;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class QuoteDataService {

    @Async("quoteIoExecutor")
    public CompletableFuture<Integer> fetchPrice(long productId) {
        // Simulate data read; real apps use DB/API clients with timeouts.
        return CompletableFuture.completedFuture(200);
    }

    @Async("quoteIoExecutor")
    public CompletableFuture<Integer> fetchShipping(long addressId) {
        return CompletableFuture.completedFuture(25);
    }
}
```

When the Spring proxy intercepts the call, the method body runs on the selected executor and returns a future **already holding the result from inside the worker**; the caller receives a `CompletableFuture` representing the async call. There is no need to additionally wrap with `CompletableFuture.supplyAsync` inside each method just to get a future, because doing so can add an extra scheduling layer and use an unintended pool.

### 13.3. Orchestrator Service Composing Futures Without Blocking

File `src/main/java/com/example/quote/QuoteService.java`:

```java
package com.example.quote;

import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    private final QuoteDataService data;

    public QuoteService(QuoteDataService data) {
        this.data = data;
    }

    public CompletableFuture<Integer> calculateQuote(
            long productId, long addressId) {

        CompletableFuture<Integer> priceWithTax =
                data.fetchPrice(productId)
                        .thenApply(p -> p + p / 10);

        CompletableFuture<Integer> shipping =
                data.fetchShipping(addressId);

        return priceWithTax.thenCombine(shipping, Integer::sum);
    }
}
```

`QuoteService` **does not need** `@Async` on this orchestration method: it merely builds a pipeline from the futures already started by `QuoteDataService`; it does not use `get()`/`join()` to block. Both sources start independently, and `thenCombine` waits until both succeed.

This example works if `QuoteService` and `QuoteDataService` are **two Spring beans** invoked properly through the proxy. If `fetchPrice()` calls `this.fetchShipping()` inside the same `QuoteDataService`, the internal call may bypass the async proxy.

When exposing an HTTP endpoint, decide explicitly:

- Return the final result in the same request? Let the framework handle the response asynchronously via an appropriate return type, rather than `.join()` on the Servlet thread.
- Return `202` for long-running work and track later? You need a job ID, status, persistence/retry; `CompletableFuture` **is not a durable job queue**.
- What if `fetchPrice()` fails? The `calculateQuote()` result fails; the controller/global handler must map it to a contract-compliant error instead of silently returning a total with price `0`.

## 14. Executor Boundaries and the `commonPool` Trap

`CompletableFuture` in Spring has two ways of creating work that are often conflated:

1. **Spring `@Async("quoteIoExecutor")`:** the proxy submits the invocation to the specified **Spring bean executor**.
2. **JDK `CompletableFuture.supplyAsync(...)` or `thenApplyAsync(...)` without an executor:** defaults to the JDK's asynchronous executor mechanism (typically `ForkJoinPool.commonPool()`), **not automatically using a Spring bean**.

If a team wants all blocking I/O to go through a Spring pool with a bounded queue, use:

```java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(
                () -> blockingCall(),
                quoteIoExecutor);
```

This is an illustrative snippet requiring `Result`, `blockingCall()`, and a `quoteIoExecutor` bean reference. Do not send continuous blocking JDBC work into `ForkJoinPool.commonPool()` without understanding the pressure on other parts of the application.

A few warnings:

- `thenApply` does not guarantee running on the caller thread or the source's same worker; do not rely on thread names to protect state.
- `thenApplyAsync` does not guarantee "there will always be another free thread": the executor can reject or the queue can be full.
- `@Async` on a method does not mean `thenApplyAsync` callbacks elsewhere automatically inherit the `@Async` executor.
- If a callback wants to use request/trace/security `ThreadLocal`s, **explicit propagation and cleanup** are required. `@Transactional` in the caller does not automatically propagate to the worker; each worker needs proper transaction boundaries.
- An executor with 2 threads where a callback calls `join()` waiting on a task queued in the **same executor** can stall forever if both workers are waiting.
- `CompletableFuture` provides no system-level backpressure. Submitting 10,000 tasks to a bounded executor/HTTP client without admission control can still grow queues, cause timeouts, or trigger rejections.

## 15. Real-World Mistakes When Composing Pipelines

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `thenApply` for a future-returning function | `CompletableFuture<CompletableFuture<T>>`, hard to handle errors/wait | `thenCompose` |
| Using `thenCompose` when B is independent of A | Creates false dependency, B starts late | Start A and B early, `thenCombine` |
| Calling `.join()` inside a callback to wait on same-pool task | Holds worker, starvation/deadlock | Compose via `thenCompose`/`thenCombine` |
| Calling `.join()` immediately in an HTTP controller | Blocks request thread | Return async result or design contract-based async job |
| Thinking `allOf` returns the futures' results | `allOf` actually returns `Void` | Read results from each future after `allOf`; check errors |
| Thinking `anyOf` always returns the fastest succeeding future | It can complete exceptionally first | Choose appropriate "first normal"/fallback condition |
| Using `exceptionally(e -> null)` everywhere | Swallows errors and turns them into bad data | Classify errors, use fallback only when valid |
| Using `whenComplete` like `handle` to replace values | Does not alter values per contract | Use `handle`/`thenApply` for transformations |
| Using default `thenApplyAsync()` thinking it uses Spring's pool | Task may run on `commonPool` | Pass executor explicitly |
| Ignoring exceptionally completed futures | Background failures are not properly recorded | `whenComplete`/`handle` at observation boundary or job status |
| Using `orTimeout` thinking it cancelled the HTTP call | I/O may keep running and holding connections | Real client timeouts, cooperative cancellation, and resource cleanup |
| Calling `cancel(true)` thinking the supplier was interrupted | With `CompletableFuture`, cancel is mainly exceptional completion | Design an explicit cancellation mechanism |
| Creating uncontrolled `supplyAsync()` inside `@Async` | Double scheduling, wrong pool, hard to trace | Let proxy run method and return appropriate result future |
| One tenant fanning out thousands of unbounded branches | Exhausts connection pool, RAM, queue, downstream | Semaphore/bulkhead, batching, concurrency limits |
| Returning `202` just because a `CompletableFuture` exists in RAM | Crash loses promised work | Durable job/queue, status, and idempotency |
| Using `join()` to check `isDone` | `isDone` may be failure/cancel | Check `isCompletedExceptionally` and handle `CompletionException` |

## 16. How to Test Pipelines

To test **composition logic** without depending on timing/sleep:

1. Use `new CompletableFuture<>()` to create incomplete sources.
2. Connect `thenApply`, `thenCompose`, or `thenCombine`.
3. Explicitly call `complete(value)` or `completeExceptionally(error)` in your desired order.
4. Use `join()`/assertions **on the test thread at the end**, not inside callbacks.
5. Verify results, errors, dependency ordering, and that callbacks do not run before sources are satisfied.

JUnit 5 example:

```java
@Test
void thenCombineWaitsForBoth() {
    CompletableFuture<Integer> left = new CompletableFuture<>();
    CompletableFuture<Integer> right = new CompletableFuture<>();

    CompletableFuture<Integer> combined =
            left.thenCombine(right, Integer::sum);

    left.complete(10);
    assertFalse(combined.isDone());

    right.complete(7);
    assertEquals(17, combined.join());
}
```

This is an **illustrative test snippet**, needing placement in a test class importing `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.*`, and `java.util.concurrent.CompletableFuture`, along with the JUnit 5 dependency. No `Thread.sleep` or scheduling guesswork needed.

Test additional branches:

- Source A fails, B succeeds: `thenCombine` must complete exceptionally, not compute with `null`.
- `thenCompose`: after A finishes while the function-created future is still incomplete, the combined result is also incomplete.
- `allOf`: if one branch is incomplete, the whole is incomplete; when all finish, a failed source causes `allOf` to fail.
- `anyOf`: complete first with an **exception** to verify this is not "first success."
- `handle` converting error to value: assertions must verify that this is an **intentional fallback decision**, not an unexpected business success.
- Configure a small executor queue, hold workers with a latch, and verify rejection/timeout behaves as designed.
- With `@Async`, invoke through the Spring proxy/another bean; use `@SpringBootTest`/appropriate slice to verify executor, propagation, and exceptional completion.

In production environments, run integration tests against real DBs, HTTP clients, timeouts, retry storms, and shutdown. Unit testing future logic **does not** prove job durability across restarts.

## 17. Self-Check Questions

**1.** A `CompletableFuture<Integer>` needs its result multiplied by 2 once data arrives. What should you use?  
**Answer:** `thenApply(x -> x * 2)`; the callback receives a **value** and returns another value.

**2.** After obtaining `userId`, you need to call `fetchOrdersAsync(userId)` returning `CompletableFuture<List<Order>>`. What should you use?  
**Answer:** `thenCompose(userId -> fetchOrdersAsync(userId))`, because the callback returns a stage.

**3.** Fetch exchange rate and shipping fee from two independent sources, then add/merge them. What should you use?  
**Answer:** Start both, then `thenCombine` when both are ready.

**4.** `allOf(f1, f2)` returns `CompletableFuture<List<T>>` — true or false?  
**Answer:** False. It returns `CompletableFuture<Void>`; read each future's result after the whole group completes normally.

**5.** Does `anyOf(f1, f2)` guarantee skipping failed futures and returning a successful result?  
**Answer:** No. The first future completing exceptionally can cause `anyOf` to complete exceptionally.

**6.** What is the difference between `thenApply` and `thenApplyAsync` without passing an executor?  
**Answer:** `thenApply` uses non-async completion rules; `thenApplyAsync` defaults to `CompletableFuture`'s async executor (usually the common pool), not automatically a Spring pool.

**7.** Does `orTimeout(1, SECONDS)` stop a running JDBC query?  
**Answer:** No. It completes the future exceptionally upon timeout; client/driver/resource-level timeouts/cancellations are needed to actually stop real work.

**8.** An `@Async` service returns `CompletableFuture`, but the caller calls `join` immediately in the controller. Is the controller completely non-blocking?  
**Answer:** No. `join` can still block the caller thread.

**9.** `handle` and `whenComplete` both accept `(value, error)`; can they be used completely interchangeably?  
**Answer:** No. `handle` **transforms** the result/error into a new stage; `whenComplete` is for **observation** and usually preserves the original result/error.

**10.** A callback calls `join()` waiting on a task sitting in the same single-worker executor; what is the risk?  
**Answer:** Starvation/deadlock because the sole worker is waiting instead of running the queued task. Use `thenCompose` and avoid blocking inside continuations.

## 18. Conclusion and Official References

**`CompletableFuture` is valuable because it expresses a dependency graph between steps:**

- **Sequential dependency:** `thenApply` for synchronous transformations, `thenCompose` when the next step returns a future.
- **Parallel combining:** `thenCombine` for two independent sources; `allOf` for multiple sources.
- **Branching:** `anyOf` when wanting the earliest completed result while accepting possible failure; pick another API if wanting "first success."
- **Errors:** `exceptionally`, `handle`, `whenComplete`, along with clear error boundaries.
- **Executors:** non-Async and Async callbacks have different scheduling behavior; pass an executor explicitly when resource control is needed.
- **Operations:** avoid `join` inside workers, use real timeouts/cancellations, bound concurrency, observe failed futures; `CompletableFuture` does not replace a durable job queue.

References:

- [Java SE 17 — `CompletableFuture` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): all combinators, errors, timeouts, cancellation, and executor rules.
- [Java SE 17 — `CompletionStage` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): stage and dependency concepts.
- [Java SE 17 — `ExecutorService` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): execution management and shutdown.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, futures, executors, and exception handling.
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): why self-invocation bypasses async proxies.