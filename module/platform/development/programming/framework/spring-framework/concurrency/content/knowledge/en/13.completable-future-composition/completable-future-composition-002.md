# thenCombine() Combines Two Independent Results

> **Module:** Spring Framework – concurrency  
> **Knowledge Group:** `CompletableFuture` Composition  
> **Focus:** `thenCombine()` is used to **combine the results of two tasks that have no data dependency on each other**, after both `CompletionStage` instances complete normally. It creates **a new stage**, does not start the two tasks itself, does not require waiting sequentially with `get()`/`join()`, and does not guarantee that both tasks always run on two different threads.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Accurately explain the execution condition of `thenCombine`, the parameter types of the `BiFunction`, and the `CompletableFuture<V>` return type.
2. Create two independent `CompletableFuture` instances with `supplyAsync` or receive them from two async APIs and combine them into a strongly typed result.
3. Distinguish "independent" from "parallel", and distinguish `thenCombine` from `thenCombineAsync`.
4. Predict behavior when one or both upstreams fail, are cancelled, never complete, or when the combiner function itself throws an exception.
5. Intentionally apply `exceptionally`, `handle`, `whenComplete`, timeouts, and cancellation.
6. Use `thenCombine` in a Spring service coordinating two data sources without blocking request threads or losing error observability.
7. Know when to use `thenCompose`, `thenApply`, `allOf`, or `applyToEither` instead of `thenCombine`.
8. Run Java 17 and Spring Context examples with deterministic output, along with tests that do not rely on `Thread.sleep()`.

## 2. The Problem: Two Independent Results, One Combined Response

Suppose an endpoint needs to return a quote consisting of:

- **Product info**: service A returns the product name by ID.
- **Current price**: service B returns the price for the same ID.
- **Final quote**: merges the name and price into a `Quote`.

Calls A and B only need the same product ID; neither needs A's result to start B. Therefore, they can be **started independently** and their results combined after both finish.

The easy-to-write approach that can cause sequential waiting:

~~~java
String product = productClient.fetchName(id);  // May block.
int price = pricingClient.fetchPrice(id);      // Only called after the previous step.
return new Quote(product, price);
~~~

This is **Java pseudocode inside a synchronous service**, assuming both clients exist. If each call takes around 300 ms and 500 ms, without overlap the total time is typically around 800 ms plus overhead.

If both APIs already support asynchronous calls:

~~~java
CompletableFuture<String> nameFuture = productClient.fetchNameAsync(id);
CompletableFuture<Integer> priceFuture = pricingClient.fetchPriceAsync(id);

CompletableFuture<Quote> quoteFuture =
        nameFuture.thenCombine(priceFuture, Quote::new);
~~~

This is a **snippet for an application with two async clients and a Quote record/class**, not a standalone program. `quoteFuture` only has a value after both sources complete normally.

Diagram:

~~~text
                              +--> fetchNameAsync(id) ----> "Book" ---+
Request / orchestration ------|                                      | 
                              +--> fetchPriceAsync(id) ----> 50 -----+--> thenCombine
                                                                            |
                                                                            v
                                                                  Quote("Book", 50)
                                                                            |
                                                                            v
                                                                  CompletableFuture<Quote>
~~~

The key point is **not waiting to get A's result before submitting B**. However, this structure only enables time overlap; if the backend, connection pool, or executor only allows one task to run at a time, the two tasks can still execute sequentially.

## 3. API Signature and Meaning of Each Component

For `CompletableFuture<T>`:

~~~java
<U, V> CompletableFuture<V> thenCombine(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);
~~~

Meaning:

- **`T`:** result type of the left stage (`this`).
- **`U`:** result type of the `other` stage.
- **`V`:** result type produced by the combiner function `fn`.
- **`other`:** an independent `CompletionStage` whose result is needed.
- **`fn`:** a function taking **two values** and returning **one value**; for example `(name, price) -> new Quote(name, price)`.
- **Return value:** a **new** `CompletableFuture<V>` representing the combined operation.

The Java Javadoc states that the new stage executes the function when **both stages complete normally**. "Complete normally" means completed without an exception or cancellation—it does not mean the result must be non-`null`.

### Minimal Example

~~~java
CompletableFuture<Integer> left =
        CompletableFuture.completedFuture(20);
CompletableFuture<Integer> right =
        CompletableFuture.completedFuture(22);

CompletableFuture<Integer> total =
        left.thenCombine(right, Integer::sum);

System.out.println(total.join());
~~~

This is a **Java snippet** placed inside a method with `import java.util.concurrent.CompletableFuture`. Output:

~~~text
42
~~~

Because both inputs are already complete, the addition will very likely execute **immediately upon registering the continuation**; that is valid behavior. Do not assume "with CompletableFuture, every callback always runs on a worker".

### What Does thenCombine NOT Do?

- It does not call `supplyAsync` or create tasks for `left`/`right` on its own.
- It does not guarantee running the combiner function on a separate thread.
- It does not decide which executor processes the two previously created sources.
- It does not block the caller to wait for both inputs like two `get()` calls; however, **the combiner function can run inline upon registration** if both are already finished, so if `fn` is heavy or blocking, the registration call itself can take time.
- It does not make upstream failures "disappear"; the new stage completes exceptionally when a normal combined result cannot be produced.
- It does not guarantee that cancelling the new stage will cancel the input sources.

## 4. Completion Rules and Execution Order

### 4.1. When Both Succeed

~~~text
left:  ---- running ------------> completed("A")
right: ---- running -----> completed(10)

thenCombine(left, right, (a, b) -> a + b)
                                |
                         both values ready
                                |
                                v
                           completed("A10")
~~~

The `BiFunction` receives results **by parameter position**: the first parameter comes from the stage on which `thenCombine` is called, and the second parameter comes from `other`. **Who finishes first** does not flip parameter order:

~~~java
CompletableFuture<String> name = ...;
CompletableFuture<Integer> price = ...;

CompletableFuture<String> label = name.thenCombine(
        price, (n, p) -> n + " : " + p);
~~~

**Illustrative snippet:** the futures must already be created beforehand. Even if `price` finishes first, `n` is still the name and `p` is still the price.

### 4.2. When Only One Result Is Ready

When `left` is completed but `right` is not yet completed, `thenCombine` **does not have both values yet**, so `fn` cannot run. The resulting future remains pending, unless an exception/cancellation case is handled by the implementation according to completion rules.

A standard way to test this is to create two `new CompletableFuture<>()`, complete one source at a time, and observe `isDone()` on the new stage.

### 4.3. When Both Completed Before Registration

If both `CompletableFuture.completedFuture(...)` instances are already completed, the **non-Async `thenCombine`** variant can run `fn` directly on the thread calling `thenCombine`. The contract does not reserve a separate worker thread for this continuation.

Therefore, do not put a blocking HTTP call or very heavy CPU computation inside a non-Async `thenCombine` if the call site needs low latency. If you need to isolate resources for the aggregation step, consider `thenCombineAsync(..., executor)` with a dedicated, managed executor.

### 4.4. What If Two "Independent" Inputs Share a Single-Thread Executor

~~~java
ExecutorService single = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 20, single);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 22, single);

CompletableFuture<Integer> result =
        a.thenCombine(b, Integer::sum);
~~~

This is a **snippet**; `single` must be shut down in an application. Because both tasks use the same single-thread executor, they may execute one after the other. The result is still 42, but you should not describe them as two CPU jobs truly running in parallel.

**Independent** = task A's data does not need B's result to start, and vice versa. **Parallel** = the system actually executes work concurrently across multiple resources. `thenCombine` requires logical independence, and does not provide physical parallelism by itself.

## 5. How Do thenCombine and thenCombineAsync Differ?

There are three important overloads:

~~~java
left.thenCombine(right, combiner);

left.thenCombineAsync(right, combiner);

left.thenCombineAsync(right, combiner, customExecutor);
~~~

| Usage | Condition to invoke `combiner` | Where the combiner runs |
| --- | --- | --- |
| `thenCombine` | When both sources complete normally | May run inline on the thread completing one source or the registering thread if already done; no separate thread guaranteed |
| `thenCombineAsync` without executor | Same condition | Uses the stage's default asynchronous execution facility; for standard `CompletableFuture` this is `ForkJoinPool.commonPool()`, with exceptions described in Javadoc |
| `thenCombineAsync(..., executor)` | Same condition | Dispatched on the supplied executor, such as a Spring-managed `ThreadPoolTaskExecutor` |

**Async here is a property of the combining step**, and does not alter how the two upstreams execute. Example:

~~~java
CompletableFuture<Price> price = pricingService.loadPriceAsync(id);
CompletableFuture<Stock> stock = stockService.loadStockAsync(id);

return price.thenCombineAsync(
        stock,
        (p, s) -> new Offer(p, s),
        aggregationExecutor);
~~~

This is a **snippet** requiring existing classes/services `Price`, `Stock`, `Offer`, and `aggregationExecutor`.

### When to Choose Which Variant?

- If `combiner` only constructs a DTO, adds a few numbers, or concatenates two strings, `thenCombine` is usually sufficient and avoids extra scheduling overhead.
- If `combiner` performs complex mapping or significant CPU work, `thenCombineAsync(..., executor)` with a bounded pool is an easily controlled choice.
- If the combiner performs blocking I/O, it is better to split it into **an explicit asynchronous stage** (typically `thenCompose` or `thenCombine(...).thenCompose(...)`) rather than accidentally blocking the stage-completing thread.
- Do not default to the common pool for heavy blocking I/O; thread starvation can affect other asynchronous work across the JVM.
- A custom-supplied `Executor` can still run inline (for example, a direct executor), so you cannot guarantee "an Async overload always uses a different thread" regardless of the concrete executor.

### Executor Rejection for the Continuation

If `thenCombineAsync` needs to schedule the combiner function but the executor has already shut down or is saturated and rejects the task, the resulting stage may complete exceptionally due to dispatch failure. That policy should be tested against the actual executor. **Do not monitor only errors from the two sources**; also monitor errors from the combining step and its scheduling.

## 6. Runnable Java 17 Example with Two Independent Sources

The program below creates **two workers** to compute separate pieces of information, uses `CountDownLatch` to hold them at a boundary before completing, and then:

1. Proves that both tasks started independently.
2. Proves that `thenCombine` has not finished before both results are ready.
3. Receives the combined result via `thenCombine`.
4. Runs another combination via `thenCombineAsync(..., aggregationExecutor)` and observes the exact configured thread.
5. Tests one source failing and recovering with `exceptionally`.

### 6.1. ThenCombineDemo.java

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenCombineDemo {

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("latch timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService fetchPool = Executors.newFixedThreadPool(2);
        ExecutorService aggregatePool =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "aggregate-worker"));

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> name =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        await(release);
                        return "Book";
                    }, fetchPool);

            CompletableFuture<Integer> price =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        await(release);
                        return 50;
                    }, fetchPool);

            CompletableFuture<String> quote =
                    name.thenCombine(price,
                            (n, p) -> n + "-" + p);

            CompletableFuture<String> asyncQuote =
                    name.thenCombineAsync(
                            price,
                            (n, p) -> n + "-" + p
                                    + "@" + Thread.currentThread().getName(),
                            aggregatePool);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("tasks did not start");
            }

            System.out.println("both started = true");
            System.out.println("quote done before release = "
                    + quote.isDone());

            release.countDown();

            System.out.println("quote = "
                    + quote.get(5, TimeUnit.SECONDS));
            System.out.println("async quote = "
                    + asyncQuote.get(5, TimeUnit.SECONDS));

            CompletableFuture<Integer> broken =
                    CompletableFuture.failedFuture(
                            new IllegalArgumentException("price missing"));
            CompletableFuture<Integer> fee =
                    CompletableFuture.completedFuture(5);

            CompletableFuture<Integer> failed =
                    broken.thenCombine(fee, Integer::sum);

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println("failure cause = "
                        + ex.getCause().getMessage());
            }

            CompletableFuture<Integer> fallback =
                    broken.exceptionally(ex -> 10)
                          .thenCombine(fee, Integer::sum);

            System.out.println("fallback total = " + fallback.join());
        } finally {
            // Clean up on the error path too so workers are not left stuck.
            release.countDown();
            fetchPool.shutdown();
            aggregatePool.shutdown();

            if (!fetchPool.awaitTermination(5, TimeUnit.SECONDS)) {
                fetchPool.shutdownNow();
            }
            if (!aggregatePool.awaitTermination(5, TimeUnit.SECONDS)) {
                aggregatePool.shutdownNow();
            }
        }
    }
}
~~~

### 6.2. Compile, Run, and Output

~~~bash
javac ThenCombineDemo.java
java ThenCombineDemo
~~~

**Program stdout on a successful run:**

~~~text
both started = true
quote done before release = false
quote = Book-50
async quote = Book-50@aggregate-worker
failure cause = price missing
fallback total = 15
~~~

### 6.3. Why Is the Output Deterministic?

- `fetchPool` has two workers so both `supplyAsync` calls can reach `started.countDown()` in this lightweight example.
- Main only passes `started.await(...)` once both sources report they have started; at that point `release` is still closed, so neither can return `"Book"` or `50` yet. Thus `quote.isDone()` at the print statement is guaranteed to be `false`.
- After `release.countDown()`, both tasks finish; `quote.get(timeout)` waits for the combined result and prints `Book-50`.
- `thenCombineAsync(..., aggregatePool)` runs the combining step on the thread named `aggregate-worker` by the factory, rather than relying on an arbitrary common pool thread name.
- `failedFuture` is an already-exceptional source, so `thenCombine` does not call `Integer::sum` to produce a result from the failed source. `join()` throws `CompletionException`, and `getCause()` reveals the message `price missing`.
- `exceptionally(ex -> 10)` recovers the **broken source** to 10, so `10 + 5 = 15`.
- Both pools are shut down in `finally` and awaited with timeouts, preventing the process from hanging because of unfinished workers.

**Limitation of the demo:** it coordinates with latches to verify ordering, not to simulate network response times. In real production, completion timing depends on the scheduler, I/O, connection limits, and load. Never use `Thread.sleep` as a test synchronization mechanism.

## 7. Typed Results: From Two Sources to a DTO/Record

A major benefit of `thenCombine` is building **a strongly typed object** from two mutually independent sources:

~~~java
record Product(String id, String name) {}
record Price(long cents, String currency) {}
record ProductView(Product product, Price price) {}

CompletableFuture<Product> productFuture = findProductAsync(id);
CompletableFuture<Price> priceFuture = findPriceAsync(id);

CompletableFuture<ProductView> viewFuture =
        productFuture.thenCombine(priceFuture, ProductView::new);
~~~

This is a **Java 17 snippet** containing three valid records when placed in an appropriate class/package scope; `findProductAsync` and `findPriceAsync` are assumed APIs, not a standalone program.

Here:

- `T = Product`, `U = Price`, `V = ProductView`.
- `thenCombine` receives `Product` and `Price` as two parameters.
- `ProductView::new` is the matching two-argument constructor reference.
- The resulting future carries the exact type `CompletableFuture<ProductView>`, without casting or storing temporarily in two shared mutable variables.

If both stages complete normally, `ProductView` is constructed exactly once for that continuation. Avoid mutating a shared mutable `ProductView` from two separate callbacks, as that easily creates race conditions and incomplete states.

### What If a Source Returns null?

`CompletableFuture.completedFuture(null)` is a **normal completion**, distinct from exceptional completion. The `BiFunction` can still be called with `null` values. If the constructor forbids nulls or business logic treats null as an error, check explicitly:

~~~java
CompletableFuture<ProductView> viewFuture =
        productFuture.thenCombine(priceFuture, (p, price) -> {
            if (p == null || price == null) {
                throw new IllegalStateException("missing product data");
            }
            return new ProductView(p, price);
        });
~~~

This is an **integration snippet**. An exception thrown from `BiFunction` causes the **combined future** to complete exceptionally; it does not implicitly change the state of `productFuture` and `priceFuture`.

## 8. Exceptions: When One or Both Upstreams Fail

`thenCombine` only invokes `fn` when **both stages complete normally**. If a source is exceptional, the combined stage will not produce a normal result from two values. Each path should be understood:

| Scenario | Is `fn` called? | Combined stage |
| --- | --- | --- |
| Both A and B succeed | Yes | Succeeds with `V`, unless `fn` throws |
| A succeeds, B fails | No | Completes exceptionally |
| A fails, B succeeds | No | Completes exceptionally |
| Both A and B fail | No | Completes exceptionally; do not rely on which order/cause is chosen when multiple errors occur |
| A and B succeed, but `fn` throws an exception | Yes, then throws | Completes exceptionally due to the combining step itself |
| One stage never completes | Lacks both results | May stay pending; design a timeout for the whole operation |

**Do not treat thenCombine as guaranteed fail-fast.** If one source has failed while the other has not yet completed, do not rely on the combined stage immediately surfacing the error. Actual rules/scheduling depend on the implementation. Apply a deadline at the API/service boundary instead of waiting unboundedly.

### 8.1. Extracting the Exception with get or join

~~~java
CompletableFuture<Integer> broken =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("no price"));
CompletableFuture<Integer> healthy =
        CompletableFuture.completedFuture(5);

CompletableFuture<Integer> total =
        broken.thenCombine(healthy, Integer::sum);

try {
    total.join();
} catch (CompletionException ex) {
    System.out.println(ex.getCause().getMessage());
}
~~~

This is a **snippet** importing `CompletableFuture` and `CompletionException`. Output:

~~~text
no price
~~~

- `join()` typically throws `CompletionException` (unchecked) for normal stage failures; `get()` typically throws `ExecutionException` (checked), and both must be unwrapped to inspect the cause.
- If a future is cancelled directly, `join/get` can throw `CancellationException`, so do not force every failure into a single exception class.
- If both sources fail, **do not rely on completion order to pick the cause**. If you need to collect both errors, design a wrapper/result type or observe each input separately.

### 8.2. Exception Inside BiFunction

~~~java
CompletableFuture<Integer> a =
        CompletableFuture.completedFuture(10);
CompletableFuture<Integer> b =
        CompletableFuture.completedFuture(0);

CompletableFuture<Integer> invalid =
        a.thenCombine(b, (x, y) -> x / y);
~~~

This is a **snippet**. Both upstreams complete normally, but dividing by 0 in the continuation produces an `ArithmeticException`, making `invalid` exceptional. Do not monitor errors only when fetching A/B; the combine/mapping/validation logic itself can also fail.

## 9. Choosing an Error Recovery (Fallback) Strategy

There are two places to put a fallback, and they have different semantics.

### 9.1. Recover Each Source Before Combining

If the price is missing, use a default price:

~~~java
CompletableFuture<Integer> safePrice =
        priceFuture.exceptionally(error -> 0);

CompletableFuture<Quote> quote =
        productFuture.thenCombine(safePrice, Quote::new);
~~~

This is a **snippet** requiring `priceFuture`, `productFuture`, and class `Quote`. Only the price source is recovered; if product lookup fails, the final stage still fails. Appropriate when business rules permit a degraded response for **a single field**.

### 9.2. Recover the Combined Result Afterward

~~~java
CompletableFuture<Quote> quote =
        productFuture.thenCombine(priceFuture, Quote::new)
                     .exceptionally(error -> Quote.unavailable());
~~~

This is a **snippet** where `Quote.unavailable()` is an assumed factory method. If **either upstream or the combiner** fails, the entire quote switches to the fallback value. You lose the ability to distinguish a missing price from a mapping error unless you log/record metrics/unwrap beforehand.

### 9.3. How handle and whenComplete Differ from exceptionally

| API | When does it run? | Does it change the result? |
| --- | --- | --- |
| `exceptionally(fn)` | When the previous stage is exceptional | Can replace the error with a fallback `T` |
| `handle((value, error) -> result)` | When the previous stage succeeds or fails | Can transform both success and failure into a new `U` |
| `whenComplete((value, error) -> ...)` | When the stage completes in either state | Usually used to observe/log/record metrics; **does not recover** a failure just by logging |
| `thenApply(fn)` | When the previous stage succeeds | Transforms one result |
| `thenCombine(other, fn)` | When both stages succeed | Combines two results |

Error observation example:

~~~java
CompletableFuture<Quote> observed =
        productFuture.thenCombine(priceFuture, Quote::new)
                     .whenComplete((value, error) -> {
                         if (error != null) {
                             logger.error("quote aggregation failed", error);
                         }
                     });
~~~

**Spring/logging integration snippet**, requiring `logger`. If `whenComplete` only logs, the future can still complete exceptionally. If the callback itself throws an error, downstream stages may receive the callback's error (depending on the initial state). Do not misuse a logging callback to swallow failures and return a wrong quote.

### Choosing Policy by Business Requirement

- Mandatory data: preserve exceptional completion and return an appropriate error to the upper layer.
- Optional data: fall back at the **specific source** and attach a degraded-result flag if the API requires it.
- Need to audit both sources: store each result in a `Result<T>` type containing both error/value or attach separate `handle` stages before combining.
- Avoid blindly doing `exceptionally(e -> null)` and continuing to build a DTO without checking, as that masks errors as hard-to-detect empty data.

## 10. Cancellation, Timeout, and Deadlines

### 10.1. Cancelling the Combined Stage Does Not Mean Cancelling Both Sources

~~~java
CompletableFuture<Quote> quote =
        productFuture.thenCombine(priceFuture, Quote::new);

quote.cancel(true);
~~~

This is a **snippet**. Cancelling `quote` does not guarantee that `productFuture` or `priceFuture` are automatically cancelled. `CompletableFuture.cancel` itself mainly controls **completion state**, not a reliable interrupt mechanism for all background tasks; the `mayInterruptIfRunning` parameter does not control interruption the way `FutureTask` does.

Conversely, when a source is cancelled, the dependent stage may complete exceptionally, but that does not replace a cleanup policy for the remaining source.

### 10.2. Setting a Timeout at the Operation Boundary

~~~java
CompletableFuture<Quote> result =
        productFuture.thenCombine(priceFuture, Quote::new)
                     .orTimeout(2, TimeUnit.SECONDS);
~~~

**Snippet**, requires importing `TimeUnit`. `orTimeout` (Java 9+) causes the `CompletableFuture` itself to receive a timeout completion if not finished within this duration; it **does not automatically stop** in-flight HTTP/database operations inside the two sources. When used on a future with multiple consumers, note that methods like `orTimeout` affect the exact future instance they are called on, rather than necessarily creating an independent copy.

With `get(2, TimeUnit.SECONDS)`, the timeout is the **caller's wait limit**; whether the future itself is completed exceptionally is a separate matter. Understand the difference between operation timeout, result-wait timeout, and the source HTTP client's timeout.

### 10.3. When a Request Has Expired

If the API no longer needs the result:

1. Enforce deadlines and cancellation policies at the orchestration layer.
2. Cancel source tasks **if** the async client's contract supports it, avoiding wasted work.
3. Release permits, connections, or subscriptions according to lifecycle rules.
4. Distinguish timeout errors from data/validation errors in metrics and responses.
5. Do not assume `future.cancel(true)` will definitely interrupt an HTTP client thread performing I/O.

Do not leave unbounded `join()` or `get()` calls on request threads when latency requirements are finite.

## 11. thenCombine vs. thenCompose, thenApply, allOf, applyToEither

| API | Model | When to use |
| --- | --- | --- |
| `thenApply(fn)` | `A -> f(A) -> B` | One result already available, synchronous transformation |
| `thenCompose(fn)` | `A -> asyncOperation(A) -> B` | Second task **depends on the result** of the first; needs future flattening |
| `thenCombine(other, fn)` | `A` and `B` independent, then `f(A, B) -> C` | Need **both results** to aggregate |
| `thenAcceptBoth(other, action)` | Two results -> `BiConsumer` | Need a side effect, returning no combined value (`Void`) |
| `runAfterBoth(other, action)` | Both stages done -> `Runnable` | Only need to wait for both without reading results |
| `allOf(a,b,c,...)` | Barrier for multiple futures | Wait for **multiple sources**, returns `CompletableFuture<Void>`, extract typed values afterward |
| `applyToEither(other, fn)` | Picks whichever source completes normally first per API semantics | Want the result from **either one**, do not need both |

### 11.1. thenCompose: Sequential Data Dependency

~~~java
CompletableFuture<Customer> customer = loadCustomerAsync(customerId);

CompletableFuture<Orders> orders =
        customer.thenCompose(c -> loadOrdersAsync(c.id()));
~~~

This is a **snippet** using assumed types/services. `loadOrdersAsync` cannot start without `c.id()`. Using `thenCombine` for this kind of dependency is wrong with respect to dependency structure; `thenCompose` eliminates the nested `CompletableFuture<CompletableFuture<Orders>>` form.

### 11.2. thenCombine: Two Independent Sources

~~~java
CompletableFuture<Customer> customer = loadCustomerAsync(customerId);
CompletableFuture<Recommendations> recommendations =
        loadRecommendationsAsync(customerId);

CompletableFuture<HomePage> page =
        customer.thenCombine(recommendations, HomePage::new);
~~~

**Snippet**: both take `customerId`, yet recommendations does not need the `Customer` object to start. Both calls can overlap in execution.

### 11.3. allOf: More Than Two Sources

~~~java
CompletableFuture<Product> product = findProductAsync(id);
CompletableFuture<Price> price = findPriceAsync(id);
CompletableFuture<Stock> stock = findStockAsync(id);

CompletableFuture<ProductPage> page =
        CompletableFuture.allOf(product, price, stock)
                .thenApply(ignored -> new ProductPage(
                        product.join(),
                        price.join(),
                        stock.join()));
~~~

This is a **snippet** requiring the corresponding business types and methods. After `allOf` completes normally, the three `join()` calls retrieve values that are already available, so they do not represent three separate sequential waits like starting each call and waiting immediately. If any source fails, `allOf` completes exceptionally and does not run the normal `thenApply`.

When there are only **two sources**, `thenCombine` is usually more concise and preserves types better without needing `join()` inside the callback.

### 11.4. Do Not Confuse with applyToEither

If the requirement is "use the result from server A or B, whichever yields a valid result first," consider `applyToEither`. It is not an API for **merging both**. With quotas, timeouts, or failing sources, inspect the exact completion semantics and choose an appropriate error strategy.

## 12. Spring Integration: Do Not Let the Controller Run Two Tasks Sequentially

### 12.1. Executor Bean and @EnableAsync

A Spring configuration for running asynchronous calls:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("io-");
        return pool; // Spring container calls initialize/destroy.
    }
}
~~~

This is a **configuration class** in a Spring project, without `main`. `@EnableAsync` enables `@Async` processing; a container-managed `ThreadPoolTaskExecutor` bean is injected/referenced by name.

The numbers are **illustrative only** and must be chosen based on connection limits, throughput, queue depth, error budgets, and downstream latency. `queueCapacity=64` means tasks may wait in the queue; it does not guarantee that two sources for one request always run at the exact same instant when the pool is busy.

### 12.2. Two Independent Services

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    @Async("ioExecutor")
    public CompletableFuture<String> getName(String productId) {
        return CompletableFuture.completedFuture("Book-" + productId);
    }
}
~~~

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    @Async("ioExecutor")
    public CompletableFuture<Integer> getPrice(String productId) {
        return CompletableFuture.completedFuture(50);
    }
}
~~~

These are **two separate Java files in a Spring application**, requiring appropriate imports, packages, and component scanning. In the example, the target method returns a `completedFuture` after finishing its computation; when invoked through a **Spring proxy**, the Spring async interceptor submits the work to the executor and the caller receives a future representing the asynchronous invocation. In a real service, the method body is typically a blocking I/O call or business operation. Do not call `this.getPrice(...)` inside the same bean expecting `@Async` to be intercepted; self-invocation bypasses the proxy by default.

### 12.3. Aggregation Service Using thenCombine

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final CatalogService catalog;
    private final PricingService pricing;

    public QuoteService(CatalogService catalog, PricingService pricing) {
        this.catalog = catalog;
        this.pricing = pricing;
    }

    public CompletableFuture<String> quote(String productId) {
        CompletableFuture<String> name =
                catalog.getName(productId);
        CompletableFuture<Integer> price =
                pricing.getPrice(productId);

        return name.thenCombine(
                price, (n, p) -> n + " : " + p);
    }
}
~~~

This is a **service component** in the same application, with no standalone `main`. Calling `catalog.getName` then `pricing.getPrice` **does not mean waiting for the first task to finish**: both calls return futures without calling `join` before starting the second call. If an invocation is rejected **at submission time** (for instance, the executor is already shut down), synchronous error handling is needed at the orchestration layer; if one of the futures fails later, the combined future reflects the failure.

### 12.4. Controller Returning CompletableFuture

In Spring MVC, you can return a `CompletableFuture` so the framework handles the async result natively:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {
    private final QuoteService quotes;

    public QuoteController(QuoteService quotes) {
        this.quotes = quotes;
    }

    @GetMapping("/quotes/{id}")
    public CompletableFuture<String> get(@PathVariable String id) {
        return quotes.quote(id);
    }
}
~~~

**This is a Spring MVC snippet**, requiring web starter/dependencies, not a standalone Java 17 file. Avoid forcing the controller to call `quote(id).join()` without a timeout when the request follows the async model; doing so blocks the servlet thread and can negate overlap/resource-release benefits. Provide exception mapping matching the HTTP contract and deadline.

### 12.5. Why Do @Async and thenCombine Not Replace Each Other?

- `@Async`/`supplyAsync` determines **how a task is launched** onto an executor.
- `thenCombine` determines **result dependency**: combining A and B after both complete normally.
- `thenCombineAsync(..., executor)` adds the choice of **where the combining step runs**.
- Transaction/security/MDC management does not cross threads automatically. If context propagation is needed, use an explicit propagation mechanism instead of assuming workers share the caller's `ThreadLocal`.

## 13. Runnable Java 17 Spring Context Example with Maven

The next example **does not need Spring Boot or a Web server**: only Spring Context, creating two `@Async` beans and combining them in an orchestration bean. Output is deterministic by result, independent of the order in which the two workers log.

### 13.1. Project Structure

~~~text
spring-combine-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringCombineDemo.java
~~~

`pom.xml` using Java 17 and Spring Framework 6.2.16:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-combine-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/demo/SpringCombineDemo.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SpringCombineDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    static class Config {
        @Bean("ioExecutor")
        ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("io-");
            return pool;
        }

        @Bean
        Catalog catalog() {
            return new Catalog();
        }

        @Bean
        Pricing pricing() {
            return new Pricing();
        }

        @Bean
        QuoteService quoteService(Catalog catalog, Pricing pricing) {
            return new QuoteService(catalog, pricing);
        }
    }

    static class Catalog {
        @Async("ioExecutor")
        public CompletableFuture<String> name(long id) {
            return CompletableFuture.completedFuture("Book-" + id);
        }
    }

    static class Pricing {
        @Async("ioExecutor")
        public CompletableFuture<Integer> price(long id) {
            return CompletableFuture.completedFuture(50);
        }
    }

    static class QuoteService {
        private final Catalog catalog;
        private final Pricing pricing;

        QuoteService(Catalog catalog, Pricing pricing) {
            this.catalog = catalog;
            this.pricing = pricing;
        }

        CompletableFuture<String> quote(long id) {
            CompletableFuture<String> name = catalog.name(id);
            CompletableFuture<Integer> price = pricing.price(id);
            return name.thenCombine(
                    price, (n, p) -> n + ":" + p);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            QuoteService service = context.getBean(QuoteService.class);
            String result = service.quote(7)
                                   .get(5, TimeUnit.SECONDS);
            System.out.println("quote = " + result);
        }
    }
}
~~~

Compile and run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringCombineDemo
~~~

**Stdout produced by the demo class** (ignoring Maven/Spring logs if any):

~~~text
quote = Book-7:50
~~~

Explanation:

1. `@EnableAsync` activates proxy-based async support.
2. The `Catalog` and `Pricing` beans are called through Spring-injected bean references, not self-invocation.
3. Each `@Async("ioExecutor")` method runs on the specified executor and returns a result future.
4. `QuoteService.quote` creates both futures and then registers `thenCombine`; it does not retrieve `name.get` before creating `price`.
5. `main` waits only **at the demonstration boundary** with `get(timeout)`, without turning the service method synchronous. `AnnotationConfigApplicationContext` closes via try-with-resources, so Spring destroys the executor bean according to its lifecycle.

**Note:** the program creates two very short tasks; having two workers does not prove they literally ran simultaneously on every run. The point of this lesson is **no data dependency and merging after both stages succeed**, not benchmarking this tiny example.

## 14. Performance Pitfalls When Combining Futures

### 14.1. Joining Too Early Destroys Independence

Avoid:

~~~java
String name = catalog.getName(id).join();
int price = pricing.getPrice(id).join();
return CompletableFuture.completedFuture(name + ":" + price);
~~~

This is a **snippet**. The second call only occurs **after** `join()` on the first future finishes, so you turned independent operations into sequential ones and blocked the caller.

Prefer:

~~~java
CompletableFuture<String> name = catalog.getName(id);
CompletableFuture<Integer> price = pricing.getPrice(id);

return name.thenCombine(price, (n, p) -> n + ":" + p);
~~~

Both sources are launched before aggregation; the caller gets a future and can do other work.

### 14.2. Blocking Inside the Combiner

~~~java
return a.thenCombine(b, (x, y) -> {
    return externalClient.fetchBlocking(x, y);
});
~~~

**Dangerous snippet**, assuming `externalClient.fetchBlocking` blocks. With non-Async `thenCombine`, the thread completing the last stage can be held inside the combiner for too long. If you need a third I/O step that depends on A and B, chain another stage:

~~~java
return a.thenCombine(b, Pair::new)
        .thenCompose(pair ->
                externalClient.fetchAsync(pair.first(), pair.second()));
~~~

This is a **snippet** with application-defined `Pair`/`externalClient`. `thenCompose` flattens the future returned by the next I/O call instead of holding the continuation thread waiting.

### 14.3. Thread Starvation/Deadlock from Joining Inside a Small Pool

With a 1-worker pool, if a task running on that worker submits two more tasks to the same pool and calls `join()` waiting for them, the worker can block with no remaining workers to execute the two queued tasks. This can cause **starvation deadlock** from waiting inside the same pool.

How to avoid: use non-blocking composition, size pools properly, separate blocking I/O from CPU pools, and avoid designs where tasks inside a pool wait on child tasks submitted to the same pool without capacity to execute them.

### 14.4. Both Sources Share a Low-Limit Downstream

`thenCombine` does not create new "system capacity." If both A and B hit the same 5-connection DB pool, increasing concurrent requests can worsen latency. Limit concurrency, queue capacity, timeouts, and use circuit breakers/bulkheads appropriately rather than blindly increasing thread counts.

### 14.5. Discarding the Resulting Future

If you just write:

~~~java
nameFuture.thenCombine(priceFuture, (n, p) -> send(n, p));
~~~

**Snippet** with an assumed `send`. If `send` fails and you discard the resulting future, the continuation's failure can go unnoticed. Keep the Future, return it to the caller, or attach an observer with clear ownership. Do not treat calling `thenCombine` as a guarantee that the side effect ran successfully.

## 15. Testing Without Relying on the Scheduler

### 15.1. Testing That thenCombine Only Runs After Both Results Arrive

JUnit 5 snippet (requires corresponding imports and assertions):

~~~java
CompletableFuture<Integer> left = new CompletableFuture<>();
CompletableFuture<Integer> right = new CompletableFuture<>();

CompletableFuture<Integer> combined =
        left.thenCombine(right, Integer::sum);

left.complete(20);
assertFalse(combined.isDone());

right.complete(22);
assertEquals(42, combined.join());
~~~

No `Thread.sleep`, pool, or network needed; the test directly checks the **state conditions** of both stages.

### 15.2. Testing Reversed Completion Order

~~~java
CompletableFuture<String> name = new CompletableFuture<>();
CompletableFuture<Integer> price = new CompletableFuture<>();

CompletableFuture<String> quote =
        name.thenCombine(price, (n, p) -> n + ":" + p);

price.complete(50);
assertFalse(quote.isDone());

name.complete("Book");
assertEquals("Book:50", quote.join());
~~~

This is a JUnit snippet. Parameter order `(n,p)` does not change when `price` finishes first.

### 15.3. Testing Upstream Errors and Combiner Errors

~~~java
CompletableFuture<Integer> left = new CompletableFuture<>();
CompletableFuture<Integer> right = new CompletableFuture<>();

CompletableFuture<Integer> sum =
        left.thenCombine(right, Integer::sum);

left.completeExceptionally(
        new IllegalArgumentException("left failed"));
right.complete(2);

CompletionException ex =
        assertThrows(CompletionException.class, sum::join);
assertEquals("left failed", ex.getCause().getMessage());
~~~

This is a JUnit 5 snippet; import the types and `assertThrows/assertEquals`. With **one failing source and one succeeding source**, the cause can be verified. With **both sources failing**, do not lock the test to a specific chosen cause unless the contract specifies one.

To test a combiner exception, let both sources succeed and make `BiFunction` throw `IllegalStateException`; verify that the combined stage is exceptional while both sources remain successful.

### 15.4. Testing Executors and Performance

- With `thenCombineAsync(..., executor)`, provide an executor with a `ThreadFactory` that assigns controllable thread names and assert the thread name or use an appropriate probe; tests should wait on `Future` with a timeout.
- Test saturation/rejection of the executor supplied to the continuation.
- Use `CountDownLatch` when proving both tasks started before opening the completion gate.
- Measure p95/p99 latency, active/queued task counts, upstream errors, and combiner exceptions.
- Test cancellation, timeout, and graceful shutdown; confirm no thread or connection leaks.
- With Spring `@Async`, test calls through the bean proxy in an `ApplicationContext`; do not instantiate with `new` directly and claim async support is working.

## 16. Practical Implementation Checklist

- [ ] The two tasks truly **do not need each other's results** to start; if they do, switch to `thenCompose`.
- [ ] Both futures are created/started before waiting for results; no `join` immediately after the first future.
- [ ] `BiFunction` only combines/maps data and does not block for long on the default non-Async path.
- [ ] If the combiner is heavy, `thenCombineAsync(..., executor)` is chosen with a bounded, managed executor.
- [ ] Separate policies exist for upstream errors, combiner errors, and continuation scheduling failures.
- [ ] Fallbacks are placed on the right source or the overall result, without accidentally masking errors as `null`.
- [ ] Deadlines/timeouts exist for the whole operation and for each downstream where appropriate.
- [ ] Cancellation/cleanup of both sources is explicitly designed, without assuming cancelling the final stage cancels everything.
- [ ] Someone owns the combined Future; results are not discarded when business errors must be recorded.
- [ ] With Spring: executor bean, `@EnableAsync`/`@Async`, and calls through the proxy work properly; no self-invocation.
- [ ] No unbounded `get/join` waits on request threads or worker threads that could cause starvation.
- [ ] Connection pools, queues, thread pools, latency/error metrics, and overload behavior are verified when many requests call both sources.
- [ ] Success/error/null/timeout/cancel/reversed-order cases are tested with deterministic synchronization mechanisms.

## 17. Common Misconceptions

**1. "thenCombine runs two tasks at the same time by itself."** False. It only registers a combining dependency; the two futures must be created/launched by the source APIs.

**2. "Two independent futures definitely run in parallel."** False. They might share a single worker, or an upstream might execute synchronously; they are still independent in data.

**3. "thenCombine waits by blocking the calling thread."** Not like calling two `get()` calls. It creates a new stage. However, `BiFunction` may run inline when both are already complete; avoid blocking combiners.

**4. "thenCombineAsync makes the two source APIs async."** False. It only determines scheduling for the combining step.

**5. "thenCombine always runs on commonPool."** False. The non-Async variant can run inline; only the Async overload without an executor uses the stage's default async facility.

**6. "B finished before A, so the first parameter is B."** False. Parameters preserve the positions of `this` and `other`.

**7. "If one source fails, the combiner can still produce a partial result."** Not on the default normal path. For partial results, recover the input with `exceptionally/handle` before combining.

**8. "When one source fails, thenCombine always fails fast immediately."** Do not rely on this timing; set explicit deadlines.

**9. "whenComplete logged the error, so the combined future succeeds."** False. Observing an error does not recover it.

**10. "Cancelling the combined future automatically cancels both HTTP requests."** False unless explicit cancellation propagation is built for the async clients.

**11. "orTimeout automatically cancels downstream I/O."** False. Timeout completes the future exceptionally, while background tasks may keep running.

**12. "thenCombine is better than thenCompose in all cases."** False. `thenCompose` is for a next step that depends on a previous result; `thenCombine` is for two independent sources.

**13. "allOf returns a list of results from each future."** False. `allOf` returns `CompletableFuture<Void>`; results must be retrieved from each source after the barrier completes.

**14. "Having @Async means you don't need @EnableAsync or a proxy."** False for Spring's default async interception.

**15. "More threads always make thenCombine faster."** False when the bottleneck is DB, HTTP connections, CPU, or downstream services; increasing concurrency can cause queuing and timeouts.

**16. "The combined future doesn't need to be kept since callbacks are registered."** False if results or exceptions need to be observed or used in an API response.

## 18. Self-Check Questions

**Question 1:** What does `CompletableFuture.completedFuture(10).thenCombine(completedFuture(32), Integer::sum)` produce?

**Answer:** 42. Both sources completed normally and the combiner adds the two values.

**Question 2:** You need to fetch `userId` first and then call the order-loading API with that `userId`. Use `thenCombine` or `thenCompose`?

**Answer:** `thenCompose`; the order-loading call depends on the user lookup result.

**Question 3:** The price finishes before the product name. What is the first parameter in `name.thenCombine(price, (n,p)->...)`?

**Answer:** Still the name `n`. Parameter order comes from `this`/`other` positions, not completion time.

**Question 4:** The combiner function throws `IllegalArgumentException`, while the first two futures succeeded. What happens to the combined future?

**Answer:** It completes exceptionally; the two source futures are not implicitly turned into failed futures.

**Question 5:** Why does `thenCombineAsync(right, fn, executor)` not necessarily make APIs A and B run in parallel?

**Answer:** The executor is only for **`fn`**; the two sources are still launched by their own mechanisms and could share a single-worker pool.

**Question 6:** One input is cancelled; is `combined.join()` guaranteed to return a normal value?

**Answer:** No. The dependent stage can become exceptional due to the source's cancellation; handle it explicitly and note that cancelling the final stage does not automatically cancel the other source.

**Question 7:** Should you call `nameFuture.join()` before creating `priceFuture` on a request thread?

**Answer:** No, if the two sources are independent and you want concurrency. Create both futures first and then combine.

**Question 8:** Both upstreams are slow; does `thenCombine` have a default wait limit?

**Answer:** No automatic business deadline. Design timeouts at the async client/source and whole-operation boundaries.

## 19. Core Summary

**Formula:** start two independent sources to obtain `CompletableFuture<A>` and `CompletableFuture<B>`, then use `a.thenCombine(b, (x, y) -> combine(x, y))` to produce `CompletableFuture<C>`. The combiner runs when both sources **succeed**. The non-Async variant does not require a separate thread; the Async variant selects the default facility or the passed executor.

Use `thenCompose` when the second call **depends** on the first value; use `allOf` when you need a barrier for multiple sources. In Spring, combine `@Async`/async clients with a bounded `ThreadPoolTaskExecutor` to coordinate sources, and return the combined future to the upper layer. Do not overlook errors, timeouts, cancellation, context propagation, and queuing/waiting costs in production.

## Official References

- Java SE 17 — `CompletableFuture` (thenCombine, thenCombineAsync, exceptionally, cancel): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 17 — `CompletionStage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Spring Framework 6.2 — Task Execution and Scheduling / @Async: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Spring MVC async requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
