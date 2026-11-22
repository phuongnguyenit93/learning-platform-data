# CompletableFuture.thenCombine() for Combining Two Results in Java

## 1. The Problem: Two Independent Tasks, One Combined Result

When a business result must be produced from **two independent computations**, the sequential approach is typically to compute A, wait for A to finish, compute B, wait for B to finish, and then combine A and B. If A and B can proceed independently, that approach can unnecessarily increase response time.

For example:

- Read product price and read stock quantity independently, then build a display summary.
- Calculate merchandise cost and shipping cost independently, then calculate the total payment.
- Fetch user profile and permissions list independently, then merge them into a single result object.
- Analyze two separate data segments, then combine them into a report.

`CompletableFuture.thenCombine()` expresses an **AND** relationship: it runs the combining function **only after both input stages complete successfully**. It returns a new `CompletableFuture<V>` representing the combined result; the caller does not have to call `get()`/`join()` sequentially on each input to combine them.

```text
futureA: ----------- A succeeds ----┐
                                    ├── thenCombine(A, B) ──> C
futureB: ----- B succeeds ----------┘

C is computed only when both A and B are available.
The completion order of A/B does not determine the parameter order in the combining function.
```

This article uses only **general Java Concurrency** (JDK `java.util.concurrent`), without depending on Spring or any framework-specific CompletableFuture integration.

## 2. Data Types and the thenCombine Signature

`CompletableFuture<T>` is an implementation of `CompletionStage<T>` and `Future<T>`. It enables building processing pipelines where each step can complete in the future.

The key overloads when called on a `CompletableFuture<T>`:

```java
<U, V> CompletableFuture<V> thenCombine(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);

<U, V> CompletableFuture<V> thenCombineAsync(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);

<U, V> CompletableFuture<V> thenCombineAsync(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn,
        Executor executor);
```

This is an **illustrative API signature snippet**, not a standalone Java interface.

- `T`: the result type of the left-hand stage, i.e., the receiver of the method call.
- `U`: the result type of the `other` stage.
- `V`: the result type after combining.
- `BiFunction<T, U, V>`: a function that takes **two succeeded values** and returns **one new value**.
- `other`: a `CompletionStage`, not necessarily the exact `CompletableFuture` implementation type.
- The return type when called on `CompletableFuture` is a **new** `CompletableFuture<V>`. The two input futures do not have their results modified just because they are combined.

Minimal example:

```java
CompletableFuture<Integer> price =
        CompletableFuture.completedFuture(100);
CompletableFuture<Integer> shipping =
        CompletableFuture.completedFuture(20);

CompletableFuture<String> invoice = price.thenCombine(
        shipping,
        (p, s) -> "Total = " + (p + s));

System.out.println(invoice.join()); // Total = 120
```

This snippet is a fragment; to run it standalone, you need `import java.util.concurrent.CompletableFuture;` and a suitable `main` method.

**Important:** `thenCombine` **does not create two tasks by itself**. It only attaches the combining step to two existing stages. If both are created with `completedFuture` as in the example, the combining function may run immediately on the calling thread; no parallelism is introduced. Parallelism occurs when sources A and B are already arranged to run independently, such as via `supplyAsync`.

## 3. Execution Order and Trigger Conditions

Suppose:

```java
CompletableFuture<String> a = ...;
CompletableFuture<Integer> b = ...;

CompletableFuture<String> combined =
        a.thenCombine(b, (name, count) -> name + ":" + count);
```

This is a fragment with two application-defined sources `a` and `b`.

There are three termination categories to distinguish:

| State of A | State of B | Behavior of the combined stage |
| --- | --- | --- |
| Succeeded | Succeeded | Invokes `BiFunction` exactly once and completes with value `V`, unless the function throws an error |
| Succeeded | Failed | Does not invoke the combining function; the combined stage completes exceptionally |
| Failed | Succeeded | Does not invoke the combining function; the combined stage completes exceptionally |
| One/both cancelled | Either state for the other | Cancellation is exceptional completion; the dependent stage does not produce a successful combined value |
| Both succeeded, but `BiFunction` throws an error | Both sources succeeded | The combined stage completes exceptionally with the combining function's own error |

Do not assume `thenCombine` has **fail-fast** semantics like a race mechanism. When one input fails, Java does not guarantee that the dependent stage completes immediately if the other input is still pending; the implementation may trigger dependent behavior only after both inputs have completed under the "both" contract. Therefore, set an overall deadline or handle errors/cancellation proactively if you cannot wait for the remaining source.

The two successful stages can complete in either order. However, in `a.thenCombine(b, (x, y) -> ...)`, `x` is always the result of `a`, and `y` is always the result of `b`. Do not confuse "whichever finishes first" with the first parameter.

### Distinguishing a null Result from a Failure

A stage can complete normally with `null`. `thenCombine` can still invoke `BiFunction` with a `null` argument; if the callback does not handle `null`, it may throw a `NullPointerException`, causing the **combined stage** to fail. A successful `null` value is **not the same** as exceptional completion.

If non-null constraints are needed, validate inputs, use `Optional`, or translate errors appropriately at application boundaries rather than assuming stage results are always non-null.

## 4. Standalone Java 17 Example: Running Two Tasks, Then Computing a Bill

This program creates two `CompletableFuture` instances using `supplyAsync` on an `ExecutorService` with two workers. The two tasks do not depend on each other. `thenCombine` formats the combined result into a string, and `join()` is called **once at the main boundary** to retrieve the final result.

Save the file `ThenCombineDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenCombineDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> productCost =
                    CompletableFuture.supplyAsync(() -> 180, pool);

            CompletableFuture<Integer> shippingCost =
                    CompletableFuture.supplyAsync(() -> 20, pool);

            CompletableFuture<String> bill =
                    productCost.thenCombine(
                            shippingCost,
                            (product, shipping) ->
                                    "Total = " + (product + shipping));

            System.out.println(bill.join());
            System.out.println("Product = " + productCost.join());
            System.out.println("Shipping = " + shippingCost.join());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac ThenCombineDemo.java
java ThenCombineDemo
```

Stdout:

```text
Total = 200
Product = 180
Shipping = 20
```

Why is stdout deterministic? The callbacks do not print directly from worker threads. Main prints sequentially after `bill.join()` returns, at which point both sources have completed successfully. Even if the completion order of the two sources changes, the values and order of the three printed lines remain unchanged.

**Do not automatically conclude that two computations are guaranteed to run in parallel just because there are two `supplyAsync` calls.** The executor may schedule them sequentially when workers are scarce or machine resources are constrained. What is guaranteed is that the two sources are **scheduled independently** and the combined stage depends on the results of both.

### Variant Using Different Data Types

`thenCombine` does not require both sources to have the same type:

```java
record User(long id, String name) {}
record Plan(String title, int quota) {}
record View(String name, String plan, int quota) {}

// Fragment: two stages may come from two asynchronous sources.
CompletableFuture<User> userFuture = ...;
CompletableFuture<Plan> planFuture = ...;

CompletableFuture<View> viewFuture =
        userFuture.thenCombine(planFuture,
                (user, plan) ->
                        new View(user.name(), plan.title(), plan.quota()));
```

This is a **fragment**; `record` declarations can be placed inside a class or in the same source file when compiling, and the two source futures must be initialized. The combining function should focus on data transformation; avoid blocking and hard-to-control side effects inside the callback.

## 5. How thenCombine, thenApply, and thenCompose Differ

Three operations are commonly confused:

| API | Actual inputs | When to use | Relationship type |
| --- | --- | --- | --- |
| `thenApply(fn)` | One stage with a result | Transform `T → V` after a single source succeeds | Linear chain |
| `thenCompose(fn)` | One stage, function returns another stage | When the next step **depends** on the previous step's result and is itself asynchronous | Sequential dependency / flatten |
| `thenCombine(other, fn)` | Two independent stages | When **both** results are needed to compute `V` | AND combination |
| `thenAcceptBoth(other, action)` | Two independent stages | When both results are needed but **no return value V is needed** | Two inputs → `Void` |
| `runAfterBoth(other, runnable)` | Two stages | When you only need to know both succeeded, **without using their values** | Two inputs → `Void` |
| `allOf(a,b,...)` | N stages | Wait for multiple stages and design how to read each result | N inputs → `CompletableFuture<Void>` |
| `anyOf(a,b,...)` | N stages | Completes when **any** stage completes, including with an error | OR, not "one succeeded" |

### thenApply: Transforming a Single Result

```java
CompletableFuture<Integer> base =
        CompletableFuture.completedFuture(10);

CompletableFuture<Integer> doubled =
        base.thenApply(x -> x * 2);
```

`doubled.join()` produces 20. There is no second independent source to combine.

### thenCompose: Next Step Depends on the Previous Step

```java
CompletableFuture<String> orderId =
        CompletableFuture.completedFuture("O-7");

CompletableFuture<Integer> amount =
        orderId.thenCompose(id ->
                CompletableFuture.supplyAsync(() -> id.length() * 10));
```

This fragment creates an inner stage only **after** `id` is known. `thenCompose` "flattens" `CompletableFuture<CompletableFuture<Integer>>` into `CompletableFuture<Integer>`. Do not use `thenCombine` if B **needs the output of A before it can even start**.

### thenCombine: Two Sources Already Exist or Can Start Independently

```java
CompletableFuture<Integer> subtotal = ...;
CompletableFuture<Integer> tax = ...;

CompletableFuture<Integer> total =
        subtotal.thenCombine(tax, Integer::sum);
```

The `...` in the first two lines are placeholders for an illustrative snippet, **not a standalone program**. The key difference: `subtotal` and `tax` are two stages that **can be initiated independently or in parallel**, and only the combining step requires both.

### Do Not Overuse allOf for Exactly Two Sources

`CompletableFuture.allOf(a, b)` returns `CompletableFuture<Void>`; to retrieve both values, you still have to access `a.join()` and `b.join()` after `allOf` succeeds. With exactly two stages and a clear `BiFunction`, `thenCombine` is usually more concise and preserves types more cleanly.

## 6. thenCombine() vs. thenCombineAsync(): Where Does the Callback Run?

This is a major source of misunderstanding. Both require two successful results, but they differ in **callback execution policy**:

- `thenCombine(other, fn)` (without `Async`): the callback may run on the thread completing one of the two inputs, or on the thread calling the combining method if both sources have already completed. **No specific thread is guaranteed**.
- `thenCombineAsync(other, fn)`: the callback is executed asynchronously using the stage's **default asynchronous execution facility**; for standard `CompletableFuture`, this is typically `ForkJoinPool.commonPool()` (with implementation fallback rules when the common pool lacks sufficient parallelism).
- `thenCombineAsync(other, fn, executor)`: the callback is submitted to the specified `executor`. This explicitly expresses the execution resource when you want control over pools and threads.

**Async here does not mean the two sources are re-run or automatically moved to the same executor.** It only controls the **combining step**. The two sources may have been created on different executors.

```java
CompletableFuture<Integer> a = CompletableFuture.completedFuture(2);
CompletableFuture<Integer> b = CompletableFuture.completedFuture(3);

CompletableFuture<Integer> c = a.thenCombineAsync(
        b,
        (x, y) -> x + y,
        combineExecutor); // Executor created and managed by the application.
```

This is a fragment; `combineExecutor` must be a properly initialized `Executor`.

### Which Overload Should You Choose?

If the combining operation is very lightweight (adding two numbers, creating a DTO, formatting a string), the non-`Async` overload is usually appropriate to avoid extra scheduling overhead. If the callback is CPU-intensive, needs load isolation, or requires resource control, consider `thenCombineAsync(..., executor)`. If the callback performs long blocking I/O, do not default to the common pool without considering contention and load limits.

Watch out for the risk: the non-Async overload can force the **thread completing an input** to do the combining work as well. If the callback is slow, it slows down a thread intended for other tasks; with GUI/event-loop threads or small worker pools, this can cause latency spikes or unwanted reentrancy.

For application-managed executors, actively shut them down according to the lifecycle and handle task rejection. If the executor is shut down before the callback is submitted, the dependent stage may complete exceptionally with an error from `RejectedExecutionException`.

## 7. Error Handling: If One Source Fails, There Is No Combined Result

The `BiFunction` **can only compute properly when both stages complete normally**. Therefore, when one source fails, the callback is not invoked; the dependent stage completes exceptionally. Likewise, when the callback itself throws an exception, `thenCombine` returns an exceptionally completed future.

Standalone Java 17 example, save as `ThenCombineFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class ThenCombineFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> ok =
                CompletableFuture.completedFuture(10);

        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("price unavailable"));

        CompletableFuture<Integer> result =
                ok.thenCombine(failed, Integer::sum);

        try {
            System.out.println(result.join());
        } catch (CompletionException exception) {
            System.out.println(
                    "Combined failed: "
                    + exception.getCause().getClass().getSimpleName());
        }

        CompletableFuture<Integer> recovered =
                result.exceptionally(error -> -1);

        System.out.println("Recovered value: " + recovered.join());
    }
}
```

Run:

```bash
javac ThenCombineFailureDemo.java
java ThenCombineFailureDemo
```

Stdout:

```text
Combined failed: IllegalStateException
Recovered value: -1
```

Explanation: `failedFuture` creates an already-failed source, so `Integer::sum` never runs. `result.join()` throws `CompletionException`, and `getCause()` is the corresponding `IllegalStateException` in this illustrative case. Then `exceptionally` converts the failure of the **combined stage** into the fallback value `-1`.

`exceptionally(error -> fallback)` does not mutate the original `result`; it creates a **new stage**. Other dependents can still observe the failure of the original stage if no recovery is attached to them.

### Inspecting Errors with get() and join()

| Method | Retrieving result | Common exceptions |
| --- | --- | --- |
| `join()` | Returns `T` or throws unchecked | `CompletionException` if stage computation failed; `CancellationException` if the future itself was cancelled |
| `get()` | Returns `T`, declares checked exceptions | `ExecutionException`, `InterruptedException`, `CancellationException` |
| `get(timeout, unit)` | Waits up to a deadline | Adds `TimeoutException`; does not automatically cancel |

For a stage depending on a cancelled source, you may see `CompletionException` wrapping `CancellationException` rather than `CancellationException` directly. Therefore, diagnostic logic should inspect the cause, not just match the top-level exception class thrown by `join()`.

### Callback Errors

```java
CompletableFuture<Integer> badCombine =
        CompletableFuture.completedFuture(3).thenCombine(
                CompletableFuture.completedFuture(0),
                (x, divisor) -> x / divisor);
```

This snippet is valid; `badCombine.join()` throws `CompletionException` with `ArithmeticException` as its cause. Both sources succeeded, so the failure belongs to the **combining step**. Thus, when logging, separate "source A failed", "source B failed", and "biFunction failed" if business diagnostics require it.

## 8. Recover Before Combining or After Combining?

The two choices produce different behaviors.

**Recover after combining:** one failed source causes the entire combination to fail, then returns a fallback for the **entire result**.

```java
CompletableFuture<Integer> total =
        priceFuture.thenCombine(shippingFuture, Integer::sum)
                .exceptionally(error -> 0);
```

This is a fragment; `priceFuture` and `shippingFuture` must be declared. In the example, `0` is an illustrative fallback; you should not return `0` for a real invoice when price is unavailable, as it can easily mask business errors.

**Recover each source before combining:** each source has its own replacement value; the combination can still succeed when one source fails.

```java
CompletableFuture<Integer> safePrice =
        priceFuture.exceptionally(error -> 100);
CompletableFuture<Integer> safeShipping =
        shippingFuture.exceptionally(error -> 0);

CompletableFuture<Integer> total =
        safePrice.thenCombine(safeShipping, Integer::sum);
```

This is also a fragment. Choosing a fallback must be grounded in business rules: a failed shipping fee does not automatically equal 0, and failed price data should not become a fake price if doing so could cause incorrect billing. You can use `handle` to produce a status-aware result, such as a `Success/Failure` record, and then combine intentionally.

### Observing Both Failures

`thenCombine` is not an **all-errors** collector. If both sources fail, the combined future holds only one exceptional outcome and does not promise to retain both causes. When you need to log both failures separately, attach `whenComplete` to each source or map each source to a structured result value:

```java
CompletableFuture<Integer> a = ...;
CompletableFuture<Integer> b = ...;

a.whenComplete((value, error) -> {
    if (error != null) {
        recordFailure("A", error);
    }
});
b.whenComplete((value, error) -> {
    if (error != null) {
        recordFailure("B", error);
    }
});
```

`recordFailure` is an application function, so the snippet above is a fragment. `whenComplete` is geared toward observation/side effects; exceptions thrown inside the callback also need to be controlled. Do not default to `exceptionally` just to log and accidentally alter the result contract.

## 9. Timeout: Setting a Deadline for the Final Result, Not Just Individual Sources

`thenCombine` has no overload that accepts a timeout directly. You can apply a timeout to the **combined stage** (Java 9+):

```java
CompletableFuture<Integer> combined =
        a.thenCombine(b, Integer::sum);

CompletableFuture<Integer> timed =
        combined.orTimeout(800, TimeUnit.MILLISECONDS);
```

This is a fragment; `a` and `b` are `CompletableFuture<Integer>`, and `TimeUnit` must be imported. `orTimeout(...)` completes **the called CompletableFuture itself** exceptionally with `TimeoutException` if it has not finished by the deadline, and **returns the same future**, not an independent copy. Thus `timed == combined` is `true` in this example.

When one side finishes early and the other is slow, an overall deadline prevents the caller from waiting indefinitely. However:

- `orTimeout` **does not automatically cancel** sources A and B; tasks on the source side may continue running.
- `CompletableFuture.completeOnTimeout(value, timeout, unit)` also completes **that same future** with a fallback value when the deadline expires, without automatically interrupting the underlying work.
- `get(timeout, unit)` only bounds **the caller's wait time**; it does not change the future's state when the timeout expires.
- If multiple consumers hold references to the same `combined`, calling `orTimeout` or `completeOnTimeout` alters the semantics of the **shared** future. When a timeout is needed for only one consumer branch, create a separate dependent stage and apply the timeout there, or design a wrapper with clear ownership.

A common organization pattern: set an overall request deadline, manage the `Future` handles of source tasks if they must be cancelled, and configure timeouts on network/database clients for each I/O call. A `CompletableFuture` timeout alone does not guarantee that workers have stopped or released resources.

## 10. Cancellation: Does Cancelling the Combined Result Cancel the Sources?

**Do not assume cancellation propagates downward to sources.** For `CompletableFuture`, `cancel(boolean mayInterruptIfRunning)` is equivalent to completing the future exceptionally with `CancellationException`; the `mayInterruptIfRunning` parameter **does not control interruption** for this implementation.

Therefore:

- Cancelling the `combined` stage does not guarantee that the tasks running `a` and `b` are stopped.
- Cancelling one source can cause the dependent stage to complete exceptionally, but does not automatically cancel the other source.
- `isDone()` is true for success, failure, and cancellation alike; do not treat it as a successful business outcome.
- A source being cancelled, the combined future being cancelled, the callback no longer running, and the execution thread actually exiting are **different concepts**.

If the system needs to cancel both background tasks when a deadline expires, retain separate cancellation handles from the background execution API (e.g., `Future<?>` from `ExecutorService.submit`) and request cancellation according to policy. Even then, that only sends a cooperative signal: tasks must support interruption, I/O timeouts, and cleanup. `CompletableFuture.supplyAsync` itself does not expose a handle capable of interrupting a running task the way `FutureTask.cancel(true)` does.

### Example Observing Cancellation Without Assuming Automatic Propagation

```java
CompletableFuture<Integer> a = new CompletableFuture<>();
CompletableFuture<Integer> b = new CompletableFuture<>();
CompletableFuture<Integer> both =
        a.thenCombine(b, Integer::sum);

both.cancel(true);

System.out.println(both.isCancelled()); // true
System.out.println(a.isCancelled());    // false
System.out.println(b.isCancelled());    // false
```

This is a valid fragment when `CompletableFuture` is imported. It illustrates the state of independent incomplete futures. Do not use `both.isCancelled()` as proof that the two actual tasks were interrupted.

## 11. Avoiding Blocking Inside the Combining Callback

A common mistake is calling `join()` on another task directly inside `BiFunction`:

```java
// Anti-pattern: waiting for a third task inside the callback rather than
// combining two already-available values; easily stalls workers.
CompletableFuture<Integer> result =
        a.thenCombine(b,
                (x, y) -> x + y + thirdFuture.join());
```

This fragment illustrates a design flaw. `thirdFuture` may be scheduled on the very same small worker pool currently occupied by the callback, risking thread starvation, increased latency, or dependency deadlock. Express the dependency through composition instead, such as chaining another `thenCombine` with the third future after combining the first two results:

```java
CompletableFuture<Integer> total =
        a.thenCombine(b, Integer::sum)
         .thenCombine(thirdFuture, Integer::sum);
```

This snippet assumes all are `CompletableFuture<Integer>` and `thirdFuture` has already been created. This puts the dependency relationship into the graph rather than occupying a worker thread to block.

If you need to combine a runtime-variable number of futures, `allOf` or a collection-based result-gathering design may fit better than a fixed chain of `thenCombine` calls. However, `allOf` only gives a `CompletableFuture<Void>` to wait for completion; you must read each result and handle errors afterward.

## 12. Memory Visibility and Mutable Data

`CompletableFuture` publishes completion state with appropriate synchronization; code receiving results after a stage completes can safely use data produced prior to completion under the API's concurrency contract. However, that **does not make any mutable object shared between sources thread-safe**.

For example, do not have both sources mutate a plain `HashMap` without locking. Even though `thenCombine` runs only after both sources succeed, a data race between the two sources **has already occurred earlier**.

It is better for each source to return an independent/immutable result, and have `BiFunction` combine those values:

```java
record Money(long cents) {}

CompletableFuture<Money> merchandise = ...;
CompletableFuture<Money> delivery = ...;

CompletableFuture<Money> payable =
        merchandise.thenCombine(
                delivery,
                (m, d) -> new Money(m.cents() + d.cents()));
```

This is a fragment; `Money` is a Java 17 record and the two stages are initialized by the application. Real business code must handle currency/rounding/overflow properly; this code only illustrates combining immutable results.

The combining function should be **pure and short** if possible: same inputs → same output, no mutating shared state, no I/O calls or nested locking. When I/O is needed, consider separating that processing step onto an appropriate executor.

## 13. Actual Speed: Parallel Is Not Automatically Faster

If two independent tasks take \(T_A\) and \(T_B\) respectively:

- Sequential execution costs roughly \(T_A + T_B\).
- With sufficient resources and no contention, parallel execution can approach \(max(T_A, T_B)\) plus scheduling and combining overhead.
- If there is only one worker, both may still serialize on the queue and total time will not decrease.
- If they contend for I/O, CPU, locks, or memory bandwidth, parallel execution can even be **slower**.

Do not put `System.nanoTime()` inside a callback and assume that metric represents end-to-end request latency. Measure from when the sources are created/submitted until the final stage completes, including queuing and overhead; check throughput, p95/p99, pool saturation, exceptions, and timeouts.

`thenCombineAsync` adds a callback scheduling step; it is useful when load isolation is needed, but for a callback that merely adds two numbers, the overhead can exceed the work itself. Optimize based on benchmarks of real workloads rather than treating `Async` as a promise of faster execution.

## 14. Java 17 Example: Combining Two Sources with Timeout and Recovery Policy

The following example intentionally uses two already-completed futures and creates a failed future to illustrate policy when one source fails. It does not rely on `sleep()` or scheduler timing, so the output is deterministic.

Save the file `ThenCombineRecoveryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ThenCombineRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> price =
                CompletableFuture.completedFuture(500);

        CompletableFuture<Integer> shippingError =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("shipping unavailable"));

        CompletableFuture<Integer> strict =
                price.thenCombine(shippingError, Integer::sum);

        CompletableFuture<String> strictMessage =
                strict.handle((value, error) ->
                        error == null ? "Strict: " + value
                                      : "Strict: failed");

        CompletableFuture<Integer> fallbackShipping =
                shippingError.exceptionally(error -> 30);

        CompletableFuture<Integer> fallbackTotal =
                price.thenCombine(fallbackShipping, Integer::sum);

        System.out.println(strictMessage.join());
        System.out.println("Fallback total: " + fallbackTotal.join());
        System.out.println("Original shipping failed: "
                + shippingError.isCompletedExceptionally());
    }
}
```

Run:

```bash
javac ThenCombineRecoveryDemo.java
java ThenCombineRecoveryDemo
```

Stdout:

```text
Strict: failed
Fallback total: 530
Original shipping failed: true
```

Two different policies:

- `strict` preserves the semantics "without both sources succeeding, there is no combined total." `handle` turns the final outcome into a message for demo purposes.
- `fallbackShipping` creates a **new future** that succeeds with the replacement value 30; `price.thenCombine(fallbackShipping, ...)` then returns 530.
- The original `shippingError` **remains failed**. Recovering on one branch does not alter the original error for other branches.

In a real application, the value 30 must have a valid business basis; if shipping cost is unknown, a safer approach may be to report an error or return a "total cannot be calculated yet" status rather than silently filling in a fee.

## 15. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Assuming `thenCombine` starts both sources itself | It only connects two existing `CompletionStage` instances | Create/schedule both sources independently first |
| Confusing `thenCombine` with `thenCompose` | Compose is for when the next step depends on the previous step's result | Combine two independent sources with combine |
| Calling `join()` sequentially on each future before building the graph | Blocks the coordinating thread, losing async coordination benefits | Build the pipeline, then `join/get` at the boundary where the result is needed |
| Assuming the callback always runs on a separate worker | The non-Async version may run on a source-completing or caller thread | If you need explicit resource control, use `thenCombineAsync(..., executor)` |
| Assuming `thenCombineAsync` makes both sources run in parallel | Async only schedules the combining callback | Design executor/source concurrency independently |
| Assuming one failed source always fail-fasts immediately | Dependent completion in the "both" model is not a fail-fast race mechanism | Set an overall deadline and handle failure/cancellation |
| Assuming the callback also receives exceptions to combine | `BiFunction` receives only two **successful values** | Use `handle`, `exceptionally`, `whenComplete` as needed |
| Ignoring that `null` is a valid normal result | The callback may throw an NPE | Validate null or use explicit result types |
| Treating `join()` and `get()` as throwing the same exceptions | `join` typically throws unchecked `CompletionException`, `get` throws `ExecutionException` | Distinguish their contracts |
| Using `orTimeout` and assuming A/B are stopped | Timing out a stage does not automatically cancel its sources | Manage tasks and I/O deadlines separately |
| Calling `cancel(true)` on `CompletableFuture` and expecting the thread to be interrupted | `mayInterruptIfRunning` has no interrupt effect in this implementation | Use a separate execution handle when cancellation/interruption is needed |
| Assuming cancelling `combined` automatically cancels A/B | Cancellation is not guaranteed to propagate downward to sources | Define ownership and cancellation propagation explicitly |
| Putting blocking I/O into `BiFunction` on the common pool | Can hold workers for a long time and increase contention | Use an appropriate executor, timeouts, and short callbacks |
| Having sources mutate a shared mutable object without locking | A data race occurs before the combine step | Return independent/immutable results, then combine |
| Recovering with an invalid default value | Can mask business errors | Use a contract-backed fallback or a result type that explicitly indicates missing data |

## 16. Project Checklist for Applying thenCombine

1. **Are the two sources truly independent?** If B needs A to start, use `thenCompose` instead of `thenCombine`.
2. **Do both really need to succeed?** If not, consider per-source recovery before combining or a result-envelope model.
3. **Are the data types right?** `T` and `U` can differ; choose `V` as the business result type.
4. **Who owns the executor?** Determine which pool the sources use and whether the combining callback needs its own executor.
5. **Is the combining function pure and short?** Avoid blocking, shared mutable state, long-held locks, and hard-to-rollback side effects.
6. **What is the overall deadline?** Distinguish `get(timeout)` from `orTimeout/completeOnTimeout`, noting that the latter two mutate the future they are called on.
7. **What if one source fails?** Decide between strict failure, per-source fallback, or reporting a partial result.
8. **Do you need to capture all errors?** Record errors at each source; do not expect the combined future to hold all causes.
9. **What if the user cancels the request?** `CompletableFuture` cancellation does not guarantee stopping submitted tasks; manage cancellation signals and cleanup separately.
10. **Test completion orders:** test A finishing first, B finishing first, A failing, B failing, both failing, callback throwing, null values, and timeout/cancel.
11. **Measure real performance:** check source wait time, callback time, queuing, and end-to-end latency; do not assume `Async` is faster.
12. **Keep standard Java scope:** no framework is needed to understand the `thenCombine`/`CompletionStage` contract.

## 17. Self-Check Questions

**1. Does `thenCombine` run when one of the two futures succeeds or when both succeed?**  
Only when **both** complete successfully does it invoke `BiFunction` to produce a result.

**2. If B completes before A, does the first parameter of `BiFunction` become B's value?**  
No. In `a.thenCombine(b, (x, y) -> ...)`, `x` is always A's value and `y` is always B's value.

**3. Does `thenCombineAsync` automatically move tasks A and B onto the executor provided in the three-parameter overload?**  
No. That executor schedules the **combining callback**; where A and B run is determined by how the source stages were created.

**4. When should you choose `thenCompose` instead of `thenCombine`?**  
When the next task must use the previous step's result to **create a new asynchronous stage**, such as getting a user ID first and then querying that user's permissions.

**5. If one source fails, is `BiFunction` invoked with the exception as an argument?**  
No. It is not invoked unless both sources succeed; recovery and error handling use other stages.

**6. Does `exceptionally` attached to `combined` modify the two original sources?**  
No. It creates a separate recovery stage based on `combined`'s exceptional outcome.

**7. Does `combined.orTimeout(...)` create a new `CompletableFuture`?**  
No. It returns the same `combined` instance and may complete that exact object exceptionally when the deadline expires.

**8. Does cancelling `combined` guarantee interrupting two tasks started with `supplyAsync`?**  
No. `CompletableFuture` cancellation does not guarantee interrupting or cancelling its sources.

**9. When waiting on more than two sources, can you chain multiple `thenCombine` calls?**  
Yes, for a small number with clear types. For a dynamic set of sources, consider `allOf` and an appropriate aggregation mechanism.

**10. For a callback that only adds two numbers, is using `thenCombineAsync` always better?**  
No. Extra scheduling adds overhead; `thenCombine` is usually simpler if the callback is lightweight and does not require dedicated thread control.

## References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
