# CompletableFuture: thenApply(), thenAccept(), thenRun()

## 1. Why Are Three Different Methods Needed?

`CompletableFuture<T>` in `java.util.concurrent` represents a computation that may complete later and supports **building dependent processing chains** (dependent stages). Instead of blocking the calling thread with `get()` immediately after submitting a task, you can register the next step to run **when the previous stage completes normally**.

The three commonly used methods are:

- **`thenApply(Function<? super T, ? extends U>)`**: takes the result `T`, **transforms** it into a value `U`, and returns `CompletableFuture<U>`.
- **`thenAccept(Consumer<? super T>)`**: takes the result `T` and **consumes** it via a side effect without producing a new output value; returns `CompletableFuture<Void>`.
- **`thenRun(Runnable)`**: executes an action that **does not take the result `T`** and returns no value, after the previous stage completes normally; returns `CompletableFuture<Void>`.

The key distinction is **what the callback receives and what the new stage returns**, not whether the callback runs on a new thread. All three **non-Async** variants may run on the thread that just completed the source stage or on another thread calling a completion method; you must not rely on a specific thread name.

~~~text
CompletableFuture<T> completes normally with value T
         |
         +--- thenApply(T -> U) ----> CompletableFuture<U>
         |
         +--- thenAccept(T -> void) -> CompletableFuture<Void>
         |
         +--- thenRun(() -> void) --> CompletableFuture<Void>
~~~

**Quick reminder:** need a value for further processing → `thenApply`; need to use the result without producing a new stage value → `thenAccept`; only need to know the previous step completed → `thenRun`.

This lesson uses **standard Java Concurrency** and JDK 17+ examples, without covering framework integrations.

## 2. Callbacks and Generics: A Comparison Table

| API | Functional interface | Callback parameter | Callback return | Stage return |
|---|---|---|---|---|
| `thenApply(fn)` | `Function<T,U>` | Result `T` of the source stage | `U` | `CompletableFuture<U>` |
| `thenAccept(action)` | `Consumer<T>` | Result `T` of the source stage | `void` | `CompletableFuture<Void>` |
| `thenRun(action)` | `Runnable` | **Does not receive result** of the source stage | `void` | `CompletableFuture<Void>` |

Example signatures in simplified form (not reflecting all generic wildcards in the library):

~~~java
CompletableFuture<U> next = previous.thenApply(value -> transform(value));
CompletableFuture<Void> consumed = previous.thenAccept(value -> consume(value));
CompletableFuture<Void> finished = previous.thenRun(() -> notifyFinished());
~~~

The three lines above are **illustrative** with assumed declared variables and functions, not a standalone compilable class.

**Important note on `Void`:** A stage from `thenAccept` or `thenRun` is still a real `CompletableFuture` on which you can call `join()`, `get()`, `isDone()`, `thenRun()`, `whenComplete()`, or attach error handling. If it completes normally, **`join()` returns `null`** because no business value was produced, not because the stage does not exist.

`thenApply` can return `null` from its lambda and produce a `CompletableFuture<U>` that completes normally with the value `null`; this differs from `CompletableFuture<Void>`, which indicates there is no output value. If the pipeline does not accept `null`, check or represent the result with an appropriate type (such as `Optional<T>`) instead of treating `null` as a failure.

## 3. Java 17 Example: A Sequential Chain

This example uses `completedFuture(10)` so the initial stage is already complete. This lets you observe the exact data types and results without interference from multithreaded scheduling.

Save the file **CompletableFutureChainDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureChainDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(10);

        CompletableFuture<String> mapped = source.thenApply(
                number -> "value=" + (number * 2));

        CompletableFuture<Void> consumed = mapped.thenAccept(
                value -> System.out.println("accept=" + value));

        CompletableFuture<Void> finished = consumed.thenRun(
                () -> System.out.println("run=completed"));

        finished.join();

        System.out.println("source=" + source.join());
        System.out.println("mapped=" + mapped.join());
        System.out.println("consumed result=" + consumed.join());
        System.out.println("finished result=" + finished.join());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac CompletableFutureChainDemo.java
java CompletableFutureChainDemo
~~~

Stdout:

~~~text
accept=value=20
run=completed
source=10
mapped=value=20
consumed result=null
finished result=null
~~~

**Reading the chain in order:**

1. `source` is a `CompletableFuture<Integer>` with result `10`.
2. `thenApply` receives `10` and transforms it into the string `"value=20"`; the `mapped` variable has type `CompletableFuture<String>`.
3. `thenAccept` receives the string and prints a line; the `consumed` stage has type `CompletableFuture<Void>`.
4. `thenRun` only knows that the `consumed` stage completed normally; the callback does not receive `"value=20"`.
5. `finished.join()` waits for the entire chain; `join()` on the two `Void` stages returns `null` on success.

Because the callbacks are registered on an already `completedFuture`, in this example they may run immediately upon registration. **Do not assume that every `thenApply` in an application always runs on the main thread**; runtime completion conditions determine the executing thread for the non-Async variants.

## 4. Three Independent Branches from the Same Source

`thenApply`, `thenAccept`, and `thenRun` can **all depend on the same source stage** instead of being chained sequentially. In that case, they are independent dependent stages and may execute in different orders if the source completes asynchronously.

This example uses `completedFuture` and only prints results **after `allOf(...).join()`**, so stdout does not depend on callback execution order:

Save **CompletableFutureBranchesDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureBranchesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(7);

        CompletableFuture<Integer> square =
                source.thenApply(value -> value * value);

        AtomicInteger observed = new AtomicInteger(-1);
        CompletableFuture<Void> accepted =
                source.thenAccept(observed::set);

        AtomicBoolean notification = new AtomicBoolean();
        CompletableFuture<Void> ran =
                source.thenRun(() -> notification.set(true));

        CompletableFuture.allOf(square, accepted, ran).join();

        System.out.println("square=" + square.join());
        System.out.println("observed=" + observed.get());
        System.out.println("notification=" + notification.get());
        System.out.println("source=" + source.join());
    }
}
~~~

Run:

~~~bash
javac CompletableFutureBranchesDemo.java
java CompletableFutureBranchesDemo
~~~

Stdout:

~~~text
square=49
observed=7
notification=true
source=7
~~~

**Explanation:** `thenApply` creates a new stage holding `49`; `thenAccept` writes the result into an `AtomicInteger`; `thenRun` only marks the completion event using an `AtomicBoolean`. All three depend on the same source `7`, but **do not depend on each other**. `CompletableFuture.allOf(...)` is used to wait for all three to complete. Real-world code should also consider error handling for `allOf` if one branch fails.

`thenRun` does not receive a value from `source` as a parameter. If the lambda reads an outer captured variable, that data comes from the enclosing environment (closure), **not as a parameter of the `thenRun` API**; you must ensure proper synchronization and correctness when accessing shared state.

## 5. Is the Original Result Modified?

**No.** `thenApply`, `thenAccept`, and `thenRun` all **create a new dependent `CompletableFuture`**. Attaching a callback does not replace the source's result. For example:

~~~java
// ILLUSTRATION: source is CompletableFuture<Integer>.
CompletableFuture<String> derived =
        source.thenApply(value -> "ID-" + value);
~~~

If `source` completes with `42`, `source` still holds `Integer 42`; `derived` holds `String "ID-42"` when the callback succeeds. If the callback throws an exception, **`derived`** completes exceptionally while the already succeeded `source` remains successful.

This property is essential for pipelines: you can attach different processing branches to the same source. However, **side effects on the object held by `source`** (for example, a callback mutating a shared mutable `List`) can still change observable state. Do not equate "the source `Future` is unchanged" with "all referenced data is strictly immutable".

## 6. thenApply(): Transforming Results and Preserving Composability

`thenApply` is suitable when the next step needs a **new result**:

- Mapping DTO → domain model or domain → view model.
- Converting `String` → `Integer` after valid parsing.
- Computing or normalizing a received result.
- Transforming from type `T` to type `U` for the next step.

Example:

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("123")
                .thenApply(Integer::parseInt);
int answer = parsed.join(); // 123.
~~~

This is an **illustrative snippet** that can be placed inside a method with the appropriate imports.

If `Integer.parseInt` throws `NumberFormatException`, the `parsed` stage completes exceptionally and no `Integer` is emitted. There is no implicit conversion to `null` or `0` when the lambda fails.

### Do Not Confuse thenApply with thenCompose

If the callback **returns another `Future`**:

~~~java
// lookupAsync: assumed to return CompletableFuture<User>.
// idStage: assumed to be CompletableFuture<Long>.
CompletableFuture<CompletableFuture<User>> nested =
        idStage.thenApply(id -> lookupAsync(id));
~~~

`thenApply` **does not automatically flatten** `CompletableFuture<CompletableFuture<User>>`. If the intent is to invoke a second async operation and flatten the result, use:

~~~java
CompletableFuture<User> flat =
        idStage.thenCompose(id -> lookupAsync(id));
~~~

The two snippets above are **illustrative code** with assumed `User` and `lookupAsync`; they are not standalone classes. `thenCompose` expects a function returning `CompletionStage<U>`, whereas `thenApply` only expects `U`; for a lambda returning a `Future`, `thenApply`'s `U` is that `Future` type itself.

**Do not mechanically use `thenApply(f -> f.join())` as a substitute for `thenCompose`**: blocking synchronously inside a callback can tie up a worker thread and cause deadlocks if the awaited task depends on the same executor.

## 7. thenAccept(): Consuming Results, Typically for Side Effects

`thenAccept` is suitable for actions that do not need to produce an output value:

- Writing a result to storage or a synchronized result holder.
- Updating metrics, logs, or audit records after a successful computation.
- Sending a notification or performing a final processing step that requires a `T`.
- Pushing a value to a sink, provided the sink has proper error handling and load limits.

`Consumer<T>.accept(T)` returns `void`, so this callback cannot return `U` to the next stage. After `thenAccept`, the stage type is `CompletableFuture<Void>`.

~~~java
// ILLUSTRATION: source is CompletableFuture<String>.
CompletableFuture<Void> logged =
        source.thenAccept(message -> System.out.println(message));
CompletableFuture<Void> afterLog =
        logged.thenRun(() -> System.out.println("log step finished"));
~~~

If you want to **both perform a side effect and preserve the value** for the next stage, you can use `thenApply` and return the original value after performing the action, though you should carefully consider the design of side-effecting functions:

~~~java
CompletableFuture<String> unchangedValue =
        source.thenApply(message -> {
            recordMetric(message); // Illustrates a defined application method.
            return message;
        });
~~~

When business logic only needs to observe while preserving the original result or exception for downstream steps, consider `whenComplete` — this API has different semantics and is covered in the error-handling section.

**Side effects may run on the thread completing `source`** with the non-Async variant; therefore, heavy work, blocking I/O, or long synchronous logging can slow down the thread completing the `Future`. Choose an explicit executor and concurrency limit if the sink has significant load.

## 8. thenRun(): Completion Signal Without Receiving a Value

`thenRun` is appropriate when the subsequent action does not depend on the returned data—for example, signaling that a step succeeded, updating a phase flag, or marking a unit of work complete. It shares the same execution condition as the other two methods: **the previous stage completes normally**.

Example:

~~~java
CompletableFuture<Void> notified =
        CompletableFuture.completedFuture("ready")
                .thenRun(() -> System.out.println("finished"));
~~~

`thenRun` takes no parameters, which does not mean "run immediately and independently". While `source` is pending, it waits for `source` to succeed. If `source` fails, the callback **does not run**, unless you have placed a normal recovery stage before it.

If you need handling **whether `source` succeeds or fails**, `thenRun` is not the right choice for cleanup. Consider `whenComplete((value, error) -> ...)` to observe both outcomes, or structure cleanup inside the actual task using `try/finally`.

## 9. Non-Async vs. Async: Which Thread Runs the Callback?

Each method has the following variants:

| Dependent on previous stage | Default Async | Async with specified executor |
|---|---|---|
| `thenApply(fn)` | `thenApplyAsync(fn)` | `thenApplyAsync(fn, executor)` |
| `thenAccept(action)` | `thenAcceptAsync(action)` | `thenAcceptAsync(action, executor)` |
| `thenRun(action)` | `thenRunAsync(action)` | `thenRunAsync(action, executor)` |

### Without Async

Callbacks are **not guaranteed** to run on the thread that calls the registration method, nor are they always guaranteed to run on the thread executing `source`. By `CompletableFuture` policy, a non-Async dependent action may be executed by the thread completing the current `CompletableFuture` or by another thread calling a completion method. For an already completed source, the callback may run synchronously during registration; if there are multiple branches, there is no guarantee on execution order among them.

Do not write code assuming thread-local transactions or contexts will automatically propagate across stages. If context is needed, pass or manage it explicitly.

### Async Without an Executor

In standard `CompletableFuture`, async methods **without an explicit executor** typically use `ForkJoinPool.commonPool()` in normal configurations. The JDK documentation also notes an exception: when the common pool does not support a minimum parallelism level, the implementation may create a new thread for each task; therefore, never treat a fixed thread name as a contract.

### Async With an Executor

Passing a specific `Executor` gives you control over policy, concurrency, queuing, rejection, and callback lifecycle. **Async does not mean creating a dedicated thread per stage**; the executor decides how execution happens. If the executor has been shut down or rejects the task, the dependent stage can complete exceptionally; failures must be handled.

### Java 17 Example: Dedicated Executor to Verify Thread Name

Save the file **CompletableFutureAsyncDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CompletableFutureAsyncDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "lesson-worker"));

        try {
            CompletableFuture<Void> chain =
                    CompletableFuture.supplyAsync(
                            () -> "java", executor)
                    .thenApplyAsync(String::toUpperCase, executor)
                    .thenAcceptAsync(
                            value -> System.out.println(
                                    "accept=" + value + " on "
                                    + Thread.currentThread().getName()),
                            executor)
                    .thenRunAsync(
                            () -> System.out.println(
                                    "run on "
                                    + Thread.currentThread().getName()),
                            executor);

            chain.join();
            System.out.println("completed=" + chain.isDone());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac CompletableFutureAsyncDemo.java
java CompletableFutureAsyncDemo
~~~

Stdout:

~~~text
accept=JAVA on lesson-worker
run on lesson-worker
completed=true
~~~

Because every async stage in the chain uses the exact same single-thread executor with the specified thread name, the example verifies the executing thread. Calling `chain.join()` in `main` waits for the chain to finish; this **does not turn the callbacks into a synchronous API**, it only synchronizes at the boundary of the sample program.

**Do not shut down the executor too early:** if you shut it down before dependent stages have been scheduled, some stages may be rejected. In the example, `main` waits for `chain.join()` before shutting down. In real applications, clearly own the executor and handle both error and cancellation cases before shutting it down.

## 10. When the Source or Callback Fails

`thenApply`, `thenAccept`, and `thenRun` all execute their callbacks only when the source completes **normally**. When the source completes **exceptionally**, the callback is not executed; the dependent stage completes exceptionally and propagates the error. If the callback itself throws an exception, the **dependent stage** becomes exceptional, while the already succeeded source is not retroactively altered.

| Case | Does callback on source run? | Dependent result |
|---|---|---|
| Source succeeds | Yes | Result `U` or `Void` if callback succeeds |
| Source succeeds, callback throws exception | Yes | Dependent completes exceptionally |
| Source completes exceptionally | No | Dependent completes exceptionally |
| Source is cancelled | No | Dependent completes exceptionally (may observe `CompletionException` wrapping `CancellationException`) |
| Previous stage recovered successfully | Yes | Runs on the normal recovered result |

**`join()` vs. `get()`:** `join()` typically throws `CompletionException` (unchecked) when a stage fails; `get()` throws `ExecutionException` (checked) wrapping the cause; when a `Future` is cancelled directly, `CancellationException` may be thrown instead of a wrapper depending on the stage and propagation path. Inspect `getCause()` rather than assuming every error is a timeout.

### Java 17 Example: Source Failure and Callback Failure

Save the file **CompletableFutureErrorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureErrorDemo {
    public static void main(String[] args) {
        AtomicInteger callbacks = new AtomicInteger();

        CompletableFuture<Integer> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("source failed"));

        CompletableFuture<String> mapped = source.thenApply(value -> {
            callbacks.incrementAndGet();
            return "value=" + value;
        });

        CompletableFuture<Void> consumed = mapped.thenAccept(value ->
                callbacks.incrementAndGet());

        CompletableFuture<Void> finished = consumed.thenRun(
                callbacks::incrementAndGet);

        try {
            finished.join();
        } catch (CompletionException error) {
            System.out.println("source failure="
                    + error.getCause().getClass().getSimpleName());
        }

        System.out.println("callbacks=" + callbacks.get());
        System.out.println("source exceptional="
                + source.isCompletedExceptionally());

        CompletableFuture<Integer> successful =
                CompletableFuture.completedFuture(3);
        CompletableFuture<Integer> broken = successful.thenApply(value -> {
            throw new IllegalArgumentException("transform failed");
        });

        try {
            broken.join();
        } catch (CompletionException error) {
            System.out.println("callback failure="
                    + error.getCause().getClass().getSimpleName());
        }
        System.out.println("original exceptional="
                + successful.isCompletedExceptionally());
        System.out.println("derived exceptional="
                + broken.isCompletedExceptionally());
    }
}
~~~

Run:

~~~bash
javac CompletableFutureErrorDemo.java
java CompletableFutureErrorDemo
~~~

Stdout:

~~~text
source failure=IllegalStateException
callbacks=0
source exceptional=true
callback failure=IllegalArgumentException
original exceptional=false
derived exceptional=true
~~~

**Analysis:** The first source stage failed, so all three callbacks were skipped: `callbacks=0`. In the second branch, `source` succeeded with `3`, but `thenApply` threw `IllegalArgumentException`; only the new `broken` stage failed. This also demonstrates that **exceptions inside callbacks are not silently swallowed**.

**Note on state:** `isDone() == true` covers success, failure, and cancellation; you cannot rely on `isDone()` alone to conclude a pipeline succeeded. `isCompletedExceptionally()` reflects exceptional completion, while `isCancelled()` reflects direct cancellation on the corresponding `Future`.

## 11. Related Error-Handling APIs

The three primary methods **do not replace** recovery or observation APIs:

| API | When to use | Basic outcome |
|---|---|---|
| `exceptionally(fn)` | Need to provide a fallback value when a stage fails | Can return the pipeline to normal completion if the fallback succeeds |
| `handle((value, error) -> result)` | Need to compute a new value for **both** success and failure | Dependent can complete normally with the handled value, or fail if the handler throws |
| `whenComplete((value, error) -> ...)` | Need to observe result/error such as logging or metrics | Preserves the original result/error if the observer does not throw |
| `thenCompose(fn)` | Callback returns another `CompletionStage` | Flattens the async result instead of producing a nested future |

Example chaining recovery before `thenApply`:

~~~java
CompletableFuture<Integer> recovered =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("bad"))
                .exceptionally(error -> 0);
CompletableFuture<String> text = recovered.thenApply(
        value -> "count=" + value);
System.out.println(text.join()); // count=0
~~~

This is an **illustrative snippet** in the context of a class that has imported `CompletableFuture`. `exceptionally` recovers to `0`, so `thenApply` runs. However, only use a fallback when business rules allow it; returning `0` for a serious data error can cause the system to publish incorrect results.

**`whenComplete` can run even on failure**; `thenRun` only runs if the preceding stage succeeded. Do not place mandatory error cleanup inside `thenRun` assuming all cases will be cleaned up. For resources opened and closed inside a task, using `try/finally` or `try-with-resources` according to ownership is the reliable guarantee.

## 12. Sequential Chaining vs. Parallel Branching

Example:

~~~text
Chain:
source -> thenApply -> thenAccept -> thenRun
The next step only runs when the immediately preceding stage completes normally.

Branches:
                 +-> thenApply
source ----------+-> thenAccept
                 +-> thenRun
Each branch depends on source, not on the other branches.
~~~

**In a chain**, if `thenAccept` fails, `thenRun` after it does not run. If the source succeeds but the `thenApply` callback fails, subsequent dependent steps also receive exceptional completion.

**In branching**, one failing branch does not automatically fail the source, and does not necessarily fail sibling branches. To reach a combined decision, use `allOf`, `anyOf`, `thenCombine`, or a coordinator/cancellation strategy suited to the business requirements.

### Do Not Confuse thenRun with runAsync

`thenRun(runnable)` is a step **dependent on the success** of an existing stage. `CompletableFuture.runAsync(runnable)` is how you **start a new async task** without a source stage. Similarly, `supplyAsync(supplier)` starts an async task that returns a value.

`runAsync` is not equivalent to `thenRunAsync`: the latter is only scheduled when the previous stage completes normally.

## 13. Blocking, I/O, and Executor Selection

`CompletableFuture` stages do not automatically guarantee a non-blocking pipeline. A lambda can call a database, sleep, wait on a lock, or use `join()`, `get()`, or blocking I/O; that action **still occupies the thread executing the callback**.

Design guidelines:

1. For **short CPU-bound** transformations, `thenApply` or `thenApplyAsync` on a CPU executor may be appropriate depending on the source and latency needs.
2. For callbacks with **blocking I/O**, consider an I/O-appropriate executor or a truly asynchronous API; avoid using the common pool for uncontrolled long blocking.
3. For a downstream with connection limits, add **bounded concurrency** (e.g., `Semaphore`) and timeouts rather than creating unbounded futures just because the API is easy to chain.
4. For a dedicated executor, define **queue capacity, rejection policy, and lifecycle**; `thenApplyAsync` with an executor does not by itself create upstream backpressure.
5. Never call `join()` inside a callback waiting on a task that requires the same single-thread executor you are currently occupying: this easily deadlocks when circular dependencies exist.
6. When waiting at a synchronous boundary, use `get(timeout, unit)` or an appropriate timeout strategy to avoid waiting indefinitely.

**A `thenApply` operation is not necessarily parallel execution.** If you want to reduce latency, measure stage count, callback cost, executor queue wait time, and total request time; adding more stages can increase overhead without increasing throughput.

## 14. Correctness of Side Effects and Shared State

In `thenAccept` and `thenRun`, code often performs side effects, so pay attention to:

- **Writing to shared variables:** if multiple callbacks run concurrently, use immutable data, thread confinement, `Atomic` types, or proper synchronization. `CompletableFuture` does not make `ArrayList`, `HashMap`, or `counter++` automatically thread-safe.
- **Idempotency:** a successful callback does not mean the side effect can be safely repeated arbitrarily when a caller retries the entire pipeline. For data writes, message sending, or payments, use idempotency keys and handle outcomes according to business rules.
- **Error handling:** if a side effect fails, the `thenAccept` stage completes exceptionally; however, the external operation may have partially executed. Databases, files, and HTTP calls do not roll back automatically.
- **No branch ordering guarantee:** multiple callbacks registered on the same source have no fixed global execution order. If step B **must** run after A, chain them instead of attaching two branches and guessing the order.
- **Memory visibility:** completion mechanisms provide happens-before synchronization for consuming the completed result; however, they do not eliminate data races when concurrent callbacks mutate other uncoordinated state.

For data flowing through multiple stages, prefer **transformations returning new values** whenever possible instead of multiple mutations on a shared mutable object. Reserve `thenAccept` for genuine sinks, and handle sink errors explicitly.

## 15. Cancellation, Timeouts, and Shutdown

`CompletableFuture.cancel(...)` completes the `Future` in a cancelled state and **does not guarantee interrupting a running task**: for `CompletableFuture`, the `mayInterruptIfRunning` parameter is not used to control task interruption as in `FutureTask`. Dependent stages observe cancellation of the source as an exceptional completion, and `thenApply`/`thenAccept`/`thenRun` success callbacks do not run.

Key distinctions:

- **Cancel source:** the source enters the cancelled state; incomplete dependents may complete exceptionally, but this does not automatically "kill" other running work or undo side effects.
- **Cancel dependent:** does not by default cancel the source or sibling stages.
- **`orTimeout(timeout, unit)`**: can complete the `Future` with `TimeoutException` if not yet done; does not automatically guarantee background work stops.
- **`completeOnTimeout(value, timeout, unit)`**: completes with a fallback on timeout, but does not automatically cancel running downstream work.
- **Executor shutdown:** should occur when the owner no longer needs to submit dependent stages; a shut-down executor can reject subsequent async callbacks.

**Do not treat cancellation/timeouts as the sole load-control mechanism.** When upstream continues sending requests, a backlog of timed-out work can keep consuming CPU/I/O if background tasks do not cooperate to stop. Use per-dependency deadlines, bounded concurrency, and appropriate admission policies.

## 16. Pitfalls with Types, Exceptions, and Code Structure

| Mistake | Consequence | Correct approach |
|---|---|---|
| Expecting `thenAccept` to return value `U` | Type mismatch; callback is a `Consumer` | Use `thenApply` |
| Expecting `thenRun` to receive the source value | `Runnable` takes no parameters | Use `thenAccept` or `thenApply` |
| Transforming after `thenAccept` as if `T` is still available | New stage has type `Void` | Keep a separate `T` stage or use `thenApply` returning the value |
| Using `thenApply` with a `Future`-returning function expecting flattening | Produces `CompletableFuture<CompletableFuture<U>>` | Use `thenCompose` |
| Assuming non-Async callbacks always run on `main` | Depends on the thread completing source and runtime scheduling | Do not rely on thread names; use `Async` + executor when needed |
| Assuming `Async` creates a new thread for every callback | Executor may reuse worker threads | Choose an executor explicitly |
| Using `thenRun` for cleanup on both success and failure | Does not run when source fails | Use `whenComplete` / `try-finally` as appropriate |
| Calling `join()` between every stage | Easily blocks and loses async structure | Chain stages and wait at the boundary |
| Ignoring the `Future` returned by `thenAccept` | Sink failures may go unobserved | Retain and await/handle the returned `Future` |
| Not handling `RejectedExecutionException` | Async stage can complete exceptionally | Manage executor capacity and lifecycle |
| Attaching branches to source and assuming order | Independent callbacks can reorder | Chain sequentially when there is a dependency |
| Assuming timeout stops the background task | Task may keep running and cause side effects | Use cooperative cancellation and I/O timeouts |
| Calling `isDone()` and treating it as success | Done includes failure and cancellation | Check result or exception |

## 17. Checklist Before Using the Three Methods

Determine:

1. Does the new step **need the source value**, or only notification that it completed?
2. Does it need to emit a **new result type** for the next stage?
3. Can the callback fail, and who **handles the returned dependent `Future`**?
4. Does the task involve blocking I/O or long computation? Which executor should be used?
5. Are the steps an **ordered chain** or **independent branches**?
6. If the source or callback fails, does the recovery flow use `exceptionally`, `handle`, or `whenComplete`?
7. When a task is cancelled or times out, how are downstream work and side effects stopped or handled?
8. Is mutable state shared between callbacks?
9. Is there a risk of circular waiting/deadlock if a callback calls `join()` on another task on the same executor?
10. Have success, failure, timeout, and shutdown scenarios been tested?

**Conclusion:** `thenApply()` **takes `T` and returns `U`**; `thenAccept()` **takes `T` and returns no business value**; `thenRun()` **takes neither `T` nor returns a business value**. They create a new dependent `Future` and only run their callbacks on the normal completion path. Choose `Async`/executor variants when thread control is needed, handle errors on the returned stage, and avoid confusing side effects with result transformations.

## 18. Java SE References

- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 – CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
