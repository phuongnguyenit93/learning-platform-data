# CompletableFuture: `completedFuture()`, `supplyAsync()`, and `runAsync()` in Java

## 1. The Problem Solved by the Three Factory Methods

In Java concurrent programming, a call may have an **immediate result**, or it may need to submit a task to an executor and receive the result **later**. `CompletableFuture<T>` represents a computation that can complete with a value of type `T`, complete exceptionally, or be cancelled. It also allows chaining processing steps with `thenApply`, `thenCompose`, `thenAccept`, `thenRun`, and many other APIs.

Three very common starting points:

```java
CompletableFuture<Integer> ready =
        CompletableFuture.completedFuture(42);

CompletableFuture<Integer> computed =
        CompletableFuture.supplyAsync(() -> 21 * 2);

CompletableFuture<Void> performed =
        CompletableFuture.runAsync(() ->
                System.out.println("doing background work"));
```

These are illustrative snippets requiring `import java.util.concurrent.CompletableFuture;`. All three return a `CompletableFuture`, but they differ in **completion timing, whether a new task is created, result type, and how the code runs**.

- **`completedFuture(value)`**: creates a future that is **already completed normally** with `value`. It does not submit any lambda/task to a worker.
- **`supplyAsync(supplier)`**: submits a `Supplier<T>` for asynchronous execution; takes the value returned by `Supplier.get()` and completes the future with that value.
- **`runAsync(runnable)`**: submits a `Runnable` for asynchronous execution; the future has type `CompletableFuture<Void>`, and when the task succeeds, it completes normally with the result value `null`.

**Note:** Having `Async` in the name does not promise that the task immediately runs on another core as soon as the method returns. The task is **scheduled** through an executor; it may start early, late, or encounter a case where the executor rejects execution. The timing relationship between the caller and the worker is concurrent, with no fixed ordering without synchronization.

This lesson belongs to **Java Advance – concurrency → CompletableFuture**, using only **general Java Concurrency**, without depending on Spring or any framework.

## 2. Core Comparison Table

| Criterion | `completedFuture(value)` | `supplyAsync(supplier)` | `runAsync(runnable)` |
| --- | --- | --- | --- |
| Input | Existing value `T` | `Supplier<T>` | `Runnable` |
| Creates a task to run? | No | Yes | Yes |
| Value on successful completion | The provided `value` itself | Value returned by `get()` | `null` |
| Return type | `CompletableFuture<T>` | `CompletableFuture<T>` | `CompletableFuture<Void>` |
| State immediately when method returns | Already completed normally | May be incomplete or already completed | May be incomplete or already completed |
| Uses an executor by default? | No | Yes, if no executor is passed, uses the default mechanism | Yes, if no executor is passed, uses the default mechanism |
| Has an overload accepting `Executor`? | Not needed and does not exist | Yes | Yes |
| Failure | Factory does not run error-throwing code; value is already available | Exception/error from supplier is recorded as exceptional completion | Exception/error from runnable is recorded as exceptional completion |
| Use case | Cached result already available; synchronous fallback branch | Computation/data reading with a return value | Logging, emitting events, cleanup, side effects |

**Future state and business state are two different things.** A `CompletableFuture<Void>` completing normally only means `Runnable.run()` finished without throwing an error; it does not by itself prove that data was durably committed in another system.

## 3. What States Can a CompletableFuture Have?

A future can be in the **incomplete** state, and then transition to **normal completion**, **exceptional completion**, or **cancelled**. In `CompletableFuture`, cancellation is modeled as a form of exceptional completion (typically containing a `CancellationException`).

```text
                 INCOMPLETE
                  /   |    \
                 /    |     \
                v     v      v
        NORMAL(value)  EXCEPTIONAL(cause)  CANCELLED
```

Observation APIs:

- `isDone()` returns `true` when the future has completed with any outcome, including failure/cancellation.
- `isCompletedExceptionally()` checks for exceptional completion; **a cancelled future also falls under this case**.
- `isCancelled()` checks for cancellation.
- `get()` waits and returns the result, or throws checked/unchecked exceptions depending on the state.
- `join()` waits and returns the result; when the computation fails, it usually throws `CompletionException` (unchecked), and when cancelled, it may throw `CancellationException` directly.
- `getNow(valueIfAbsent)` returns the value immediately if completed normally, or returns the fallback when incomplete; if the future completed exceptionally, it **throws an exception** rather than returning the fallback.

`completedFuture(x)` creates the `NORMAL(x)` state **immediately**. `supplyAsync` and `runAsync` create an opportunity for the future to complete later via a task running on an executor.

Do not use `isDone()==true` as proof of success. `isDone` can be true due to failure or cancellation; to know the outcome, you must observe the value/exception.

## 4. How Does `completedFuture(value)` Work?

Signature:

```java
public static <U> CompletableFuture<U> completedFuture(U value)
```

It creates **a new CompletableFuture**, already completed normally with the passed `value`.

If you already have a value of type `T`, this method **does not recompute it**, does not invoke a `Supplier`, and does not allocate a task for processing in `ForkJoinPool`. It only creates an object representing an already-completed result.

Example:

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("cached");

System.out.println(ready.isDone()); // true
System.out.println(ready.join());   // cached
```

This is an illustrative snippet with `CompletableFuture` imported; the two output lines are `true` and `cached`.

### Example 1: already-available value, null result, and state checking

Create the file `CompletedFutureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class CompletedFutureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> answer =
                CompletableFuture.completedFuture(42);

        CompletableFuture<String> noValue =
                CompletableFuture.completedFuture(null);

        System.out.println("answer done=" + answer.isDone());
        System.out.println("answer=" + answer.join());
        System.out.println("null done=" + noValue.isDone());
        System.out.println("null result=" + noValue.join());
        System.out.println("exceptional="
                + answer.isCompletedExceptionally());
    }
}
```

Compile/run on JDK 17+:

```bash
javac CompletedFutureDemo.java
java CompletedFutureDemo
```

Output:

```text
answer done=true
answer=42
null done=true
null result=null
exceptional=false
```

**`null` is a valid normal completion result** of `CompletableFuture<T>`. That is different from an "incomplete future". Check `isDone()` or use an appropriate outcome API to avoid ambiguity.

## 5. When to Use `completedFuture`?

### Known cached value

A unified API always returns `CompletableFuture<User>` even when the data is already in memory:

```java
CompletableFuture<User> findUser(String id) {
    User cached = cache.get(id);
    if (cached != null) {
        return CompletableFuture.completedFuture(cached);
    }
    return loadUserAsync(id);
}
```

This is **illustrative code**; `User`, `cache`, and `loadUserAsync` are application-defined. The cache branch does not need to create pointless async work. The other branch can use `supplyAsync` with an appropriate executor or a genuinely async I/O API.

### Default value

```java
CompletableFuture<String> fallback =
        CompletableFuture.completedFuture("guest");
```

No dedicated worker is used just to return a string literal.

### Chaining pipelines with a unified return type

When using `thenCompose`, the callback must return a `CompletionStage<U>`; if a result is already available in one branch, `completedFuture(result)` helps keep the same return type:

```java
future.thenCompose(result -> {
    if (result.isReady()) {
        return CompletableFuture.completedFuture(result);
    }
    return enrichAsync(result);
});
```

This is an illustrative snippet with `future`, `result`, and `enrichAsync` defined by the application. This method helps **avoid unnecessary nested futures**.

### Watch out for synchronous execution of continuations

When calling a continuation **without the `Async` suffix**, such as `thenApply(fn)` on a future that is **already completed**, the callback may execute **immediately on the registering thread**. That means:

```java
CompletableFuture.completedFuture(10)
        .thenApply(value -> expensiveCalculation(value));
```

does not mean `expensiveCalculation` runs in the background. If the callback is long-running or blocking, the caller registering the callback may be held up. `completedFuture` is not responsible for turning downstream steps into asynchronous ones.

## 6. `completedFuture` Does Not Deep-Copy the Value

`completedFuture(object)` holds a **reference to the object** passed in; it does not clone the object. If the object is mutable and another thread modifies it without synchronization, the future does not automatically make that object thread-safe.

```java
List<String> data = new ArrayList<>();
data.add("A");

CompletableFuture<List<String>> future =
        CompletableFuture.completedFuture(data);

data.add("B");
// future.join() still references the same list data.
```

This is an illustrative snippet importing `java.util.*` and `CompletableFuture`. `future.join()` can observe the modified list contents because the list itself changed, **not because the future changed its result**.

If an immutable result value is needed, you can pass `List.copyOf(data)` or an immutable value object. `List.copyOf` creates a list that cannot be modified through the collection API, though it does not deep-copy mutable elements inside.

In concurrent workflows, creating an object and safely publishing it is one step; **avoiding modifying mutable objects after publication** is what helps consumers read consistently.

## 7. `supplyAsync(supplier)`: Creating an Asynchronous Computation with a Result

Common overload signatures:

```java
public static <U> CompletableFuture<U> supplyAsync(
        Supplier<U> supplier);

public static <U> CompletableFuture<U> supplyAsync(
        Supplier<U> supplier, Executor executor);
```

`Supplier<U>` is a functional interface in `java.util.function`:

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

A lambda takes no parameters and **returns a value**:

```java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(() -> {
            int a = 20;
            int b = 22;
            return a + b;
        });
```

`supplyAsync` submits the `Supplier` to the executor. When `get()` returns a value, the future completes normally with that value; if the `Supplier` throws an exception/error, the future transitions to exceptional completion.

**Difference from `completedFuture`:** A `Supplier` is **work to be executed**, not an already-available value. Therefore, `future.isDone()` right after `supplyAsync` may be true or false depending on when the task finishes. Do not write tests assuming it is **always false** immediately after the call.

## 8. `runAsync(runnable)`: Asynchronous Execution Without a Dedicated Result

Signatures:

```java
public static CompletableFuture<Void> runAsync(
        Runnable runnable);

public static CompletableFuture<Void> runAsync(
        Runnable runnable, Executor executor);
```

`Runnable` has the method:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}
```

Use `runAsync` when the goal is an action that does not need to return task data, such as performing housekeeping, triggering a side effect, preparing resources, or sending a request where the caller only needs to know **whether the action succeeded or failed**.

```java
CompletableFuture<Void> done =
        CompletableFuture.runAsync(() ->
                System.out.println("updated"));

done.join(); // null if successful.
```

Even though the Future has type `Void`, it still **carries completion, failure, and cancellation information**. Having no business return value does not mean the caller should discard the Future without tracking its outcome.

### Why can't `supplyAsync` be used with a lambda that returns nothing?

`supplyAsync` requires a `Supplier<T>` whose `T get()` method returns a value. The lambda:

```java
() -> System.out.println("hello")
```

is typically used as a `Runnable` because the `println` call expression does not return a result; it cannot be directly turned into a `Supplier<String>` for `supplyAsync` to complete with some string.

If a marker result is truly needed, you can write:

```java
CompletableFuture<Boolean> done =
        CompletableFuture.supplyAsync(() -> {
            performAction();
            return true;
        });
```

This is an illustrative snippet, with `performAction()` defined by the application. However, if `Boolean.TRUE` carries no meaningful business information, `runAsync` can express the intent more clearly.

## 9. Example 2: `supplyAsync` Returns a Result, `runAsync` Signals Completion

Create the file `SupplyAndRunAsyncDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SupplyAndRunAsyncDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        AtomicBoolean actionCompleted = new AtomicBoolean();

        try {
            CompletableFuture<Integer> number =
                    CompletableFuture.supplyAsync(() -> 21 * 2, executor);

            CompletableFuture<Void> action =
                    CompletableFuture.runAsync(
                            () -> actionCompleted.set(true),
                            executor);

            int result = number.join();
            Void actionResult = action.join();

            System.out.println("number=" + result);
            System.out.println("action value=" + actionResult);
            System.out.println("action completed="
                    + actionCompleted.get());
            System.out.println("number done=" + number.isDone());
            System.out.println("action done=" + action.isDone());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac SupplyAndRunAsyncDemo.java
java SupplyAndRunAsyncDemo
```

Output when both tasks complete normally:

```text
number=42
action value=null
action completed=true
number done=true
action done=true
```

Because `join()` is called before printing, the program does not need to predict which worker executes first. `number` yields `42` from the `Supplier`; `action` yields `null` because of the `Void` type, while still confirming that the `Runnable` finished. `AtomicBoolean` here expresses the state safely when another thread writes to it.

**Do not intentionally call `Thread.sleep(...)` to "wait for the task to finish".** `join()`/`get()` is the proper synchronization mechanism to observe completion. In production applications, waiting indefinitely is not always appropriate; timeouts/deadlines may be needed.

## 10. Default Executor When No Parameter Is Passed

With the overloads taking only `Supplier`/`Runnable`:

```java
CompletableFuture.supplyAsync(() -> compute());
CompletableFuture.runAsync(() -> update());
```

Java typically uses `ForkJoinPool.commonPool()` for these asynchronous tasks. Per `CompletableFuture`'s policy, when the common pool does not support the required level of parallelism (for example, parallelism less than two), the implementation may create a new thread for each async task instead of using the common pool.

**Do not rely on a specific thread name** like `ForkJoinPool.commonPool-worker-1`; JDK versions, JVM configurations, pools, and environments may vary.

### Advantages

- Simple task creation, minimal boilerplate.
- Suitable for short, CPU-bound work or experimentation.
- No need for a separate executor for every small example.

### Disadvantages

- The common pool is a **shared** resource that may also be used by other parts of the application, such as parallel streams.
- Long-running blocking workloads can occupy workers, affecting the latency of other tasks in the same pool.
- Difficult to control parallelism, rejection policies, thread names, workload isolation, or per-group SLAs.
- You do not manage the common pool's lifecycle the way you would with a dedicated executor you created.

**Do not call `ForkJoinPool.commonPool().shutdown()`** after a `supplyAsync` call without an executor. It is not a private resource owned by that call.

When you need thread ownership, throttling, naming, and shutdown tied to a service lifecycle, pass a **dedicated executor**.

## 11. The Executor Overload and Resource Ownership

Example:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);

CompletableFuture<Integer> result =
        CompletableFuture.supplyAsync(() -> 10 + 5, executor);

CompletableFuture<Void> action =
        CompletableFuture.runAsync(() -> doWork(), executor);
```

This is an illustrative snippet; `doWork()` is application-defined. Both tasks are submitted to the **specified executor** instead of using the default policy.

**Ownership rules:**

- The component that creates the `ExecutorService` is responsible for deciding **when to shut it down**, and can wait with `awaitTermination()`.
- A component that only receives an externally supplied `Executor` should not arbitrarily shut down a shared resource if the contract does not allow it.
- Do not create `newFixedThreadPool` per request and forget to shut it down; that can cause thread leaks.
- Do not shut down the executor too early if `thenApplyAsync`/`thenComposeAsync` stages are expected to be submitted to it later.

**Important:** `CompletableFuture.join()` waits for the future to have a result or exceptional completion, but it does not shut down the executor; finishing a task does not make the pool's workers disappear.

## 12. Example 3: Specifying a Thread Name for an Executor

Thread names help debug which executor ran a task. We can create a `ThreadFactory` for an executor owned within the scope of `main`.

Create the file `NamedExecutorDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NamedExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "lesson-worker"));

        try {
            CompletableFuture<String> name =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread().getName(),
                            executor);

            CompletableFuture<Void> action =
                    CompletableFuture.runAsync(
                            () -> {
                                String current =
                                        Thread.currentThread().getName();
                                if (!current.equals("lesson-worker")) {
                                    throw new IllegalStateException(
                                            "unexpected worker");
                                }
                            },
                            executor);

            System.out.println("supplier thread=" + name.join());
            System.out.println("runnable done=" + action.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac NamedExecutorDemo.java
java NamedExecutorDemo
```

Output:

```text
supplier thread=lesson-worker
runnable done=null
```

`NamedExecutorDemo` intentionally names the worker so the thread name output can be verified. With a single-thread executor, the two tasks are submitted sequentially and processed by the executor's worker; if the worker fails abnormally and the executor replaces it, the `ThreadFactory` still names the new thread `lesson-worker`.

**Do not overgeneralize:** just because the initial tasks ran on `lesson-worker` does not mean **every callback without the `Async` suffix on the future** will always run on that worker. A dependent stage may be executed by the thread registering the callback or the thread completing the stage, depending on circumstances.

## 13. When Does a Future Actually Complete?

`supplyAsync`/`runAsync` usually return before the task finishes running, but a very fast task **can finish right before the factory method returns**.

Therefore, the following is a weak test:

```java
var future = CompletableFuture.supplyAsync(() -> 1);
assert !future.isDone(); // Not guaranteed.
```

This is a **counterexample**. Depending on the scheduler, `future.isDone()` may already be true.

If you want to reliably demonstrate a future that is initially incomplete, use a `CountDownLatch` so the task signals it has started and then waits for a signal from the caller; check the state before releasing the latch. Do not use `sleep(100)` and hope for the best.

### Example 4: before/after state coordinated with a latch

Create the file `AsyncStateLifecycleDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncStateLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException("interrupted", e);
                        }
                        return "ready";
                    }, executor);

            started.await();
            System.out.println("before release=" + future.isDone());

            release.countDown();
            System.out.println("result=" + future.join());
            System.out.println("after join=" + future.isDone());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac AsyncStateLifecycleDemo.java
java AsyncStateLifecycleDemo
```

Output when `main` is not externally interrupted and the task completes normally:

```text
before release=false
result=ready
after join=true
```

The task signals it has started with `started.countDown()`, then waits on `release.await()`. `main` waits on `started` and reads the state while `release` is still closed, so `future.isDone()` is guaranteed to be false; after releasing the latch, the task can return `"ready"` and `join()` confirms completion.

The example uses `shutdownNow()` in `finally` to avoid forgetting cleanup if an error occurs in `main`, though **after the future has already completed** the normal path will not cancel the result that was just printed. In applications requiring graceful shutdown, choose a two-phase shutdown according to your SLA.

## 14. Result Types: `T`, `Void`, and `null`

Compare these three snippets:

```java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "OK");

CompletableFuture<Void> c =
        CompletableFuture.runAsync(() -> recordSuccess());
```

These are illustrative snippets; `recordSuccess()` is application-defined.

- `a.join()` returns `"OK"` immediately.
- `b.join()` returns `"OK"` when the `Supplier` completes; if not yet done, the caller waits.
- `c.join()` returns `null` when the `Runnable` completes normally.

**`Void` is not `void`.** `Void` is a reference type representing "no useful value"; because `CompletableFuture` is generic, `CompletableFuture<Void>` is used to represent a future whose successful result is `null`.

If a `Supplier<String>` returns `null`, then `CompletableFuture<String>` can also complete normally with `null`. Therefore, you cannot use `future.join() == null` alone to distinguish "task has not run" from "task failed". On failure, `join()` typically **throws an exception**; when incomplete, it **waits**.

## 15. Example 5: Pipeline Combining an Existing Result and an Async Task

A pipeline can start from an already-available value and then offload **a genuinely expensive step** to an executor:

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(5)
                .thenApply(value -> value + 1)
                .thenApplyAsync(value -> value * 10, executor);
```

This is an illustrative snippet; `executor` is owned by the application. `thenApply` **is not required to run on a worker**, whereas `thenApplyAsync(..., executor)` requests that the stage be scheduled through that executor.

### Full code

Create the file `CompletablePipelineDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletablePipelineDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> pipeline =
                    CompletableFuture.completedFuture(5)
                            .thenApply(value -> value + 1)
                            .thenApplyAsync(value -> value * 10, executor);

            CompletableFuture<Integer> asynchronous =
                    CompletableFuture.supplyAsync(() -> 2, executor)
                            .thenApply(value -> value + 3);

            System.out.println("pipeline=" + pipeline.join());
            System.out.println("asynchronous="
                    + asynchronous.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac CompletablePipelineDemo.java
java CompletablePipelineDemo
```

Output:

```text
pipeline=60
asynchronous=5
```

Even though the stages may run on different threads, the pure addition/multiplication in this example does not depend on execution order. The caller waits on `join()` before printing, so the output is deterministic.

**Key point:** `thenApplyAsync` differs from `supplyAsync`. `supplyAsync` starts an independent computation source from a `Supplier`; `thenApplyAsync` creates a stage that **depends on the result of the previous future** and applies a `Function` to the available value.

## 16. Turning `runAsync` into a Stage in a Workflow

`runAsync` produces a `CompletableFuture<Void>`. After the action finishes, you can use callbacks:

```java
CompletableFuture<Void> action =
        CompletableFuture.runAsync(() -> update());

CompletableFuture<String> status =
        action.thenApply(ignored -> "completed");
```

This is an illustrative snippet. The next stage is invoked when `action` completes **normally**; if `action` fails, `status` can also fail without running the success lambda.

Commonly used APIs with `CompletableFuture<Void>`:

- `thenRun(() -> audit())`: runs a `Runnable` **after** the previous stage completes normally, without receiving a value.
- `thenApply(ignored -> value)`: produces a value from the completion signal.
- `thenCompose(ignored -> nextAsync())`: chains to another async operation.
- `whenComplete((ignored, error) -> ...)`: observes the success/failure outcome.
- `handle((ignored, error) -> ...)`: transforms either the result or the error into a new value/processing branch.

Do not discard the Future just because the action "returns no result". If the side effect is important, the caller needs to **observe exceptional completion** and build retry/idempotency where appropriate.

## 17. How Are Failures in `supplyAsync` and `runAsync` Reported?

If a `Supplier`/`Runnable` throws an unhandled exception inside the task, the corresponding `CompletableFuture` typically completes **exceptionally**. The error can be retrieved via `join()` or `get()`:

- `join()` typically throws `CompletionException` with the cause at `getCause()` when the computation fails.
- `get()` throws `ExecutionException` for computation errors, in addition to `InterruptedException` if the caller is interrupted.
- For a cancelled future, `get()`/`join()` may throw `CancellationException` directly.
- Errors arising **at submission time** due to executor rejection may be reported directly at the factory method, rather than necessarily creating an exceptionally completed future.

`completedFuture(value)` does not execute exception-throwing code; it completes normally. To create a future that is **already completed exceptionally**, Java 17 provides `CompletableFuture.failedFuture(cause)`.

### Example 6: failures of `Supplier` and `Runnable`

Create the file `AsyncFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class AsyncFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> supplied =
                CompletableFuture.supplyAsync(() -> {
                    throw new IllegalArgumentException("bad input");
                });

        CompletableFuture<Void> performed =
                CompletableFuture.runAsync(() -> {
                    throw new IllegalStateException("write failed");
                });

        try {
            supplied.join();
        } catch (CompletionException e) {
            System.out.println("supply wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("supply cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("supply message="
                    + e.getCause().getMessage());
        }

        try {
            performed.get();
        } catch (ExecutionException e) {
            System.out.println("run wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("run cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("run message="
                    + e.getCause().getMessage());
        }
    }
}
```

```bash
javac AsyncFailureDemo.java
java AsyncFailureDemo
```

Output (in a normal environment without interrupting the caller):

```text
supply wrapper=CompletionException
supply cause=IllegalArgumentException
supply message=bad input
run wrapper=ExecutionException
run cause=IllegalStateException
run message=write failed
```

The two tasks can run in either order. `main` **waits on each future** and prints results in code order, so the output does not require predicting worker execution order.

**Do not "swallow" errors** by just calling `supplyAsync` or `runAsync` and discarding the Future. With `CompletableFuture`, exceptions are **recorded in the future's outcome**; you cannot rely solely on the worker's `UncaughtExceptionHandler` to know all tasks that failed.

## 18. Distinguishing Callback Errors, Task Errors, and Executor Errors

There are three different sources of failure:

**A. `Supplier`/`Runnable` throws an exception:** The task was accepted and failed while running. The future completes exceptionally and the caller can inspect the cause.

**B. Executor rejects the task:** For example, `ThreadPoolExecutor` is already shut down, or the queue is full with `AbortPolicy`. Calling `supplyAsync(..., executor)` or `runAsync(..., executor)` may throw `RejectedExecutionException` **immediately at submission time**, before the caller receives a Future.

**C. Stage callback throws an error:** `thenApply` or `thenApplyAsync` creates a **separate dependent future**. The source future may succeed while the downstream stage's future fails.

Do not lump all three together as "the root future failed". When debugging, you must know whether the error occurred in the **factory**, inside the **source task**, or in a **continuation**.

### Example 7: executor already shut down, factory rejected

Create the file `AsyncRejectionDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

public class AsyncRejectionDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        executor.shutdown();

        try {
            CompletableFuture.supplyAsync(() -> 42, executor);
        } catch (RejectedExecutionException e) {
            System.out.println("supply rejected");
        }

        try {
            CompletableFuture.runAsync(() ->
                    System.out.println("should not execute"), executor);
        } catch (RejectedExecutionException e) {
            System.out.println("run rejected");
        }

        System.out.println("shutdown=" + executor.isShutdown());
    }
}
```

```bash
javac AsyncRejectionDemo.java
java AsyncRejectionDemo
```

Output with a standard executor and default rejection policy:

```text
supply rejected
run rejected
shutdown=true
```

No async task was accepted, so no worker is executing those actions. With a `ThreadPoolExecutor` having a custom `RejectedExecutionHandler`, the behavior on rejection may differ; always check the contract of the executor being passed in.

**Note:** Checking `!executor.isShutdown()` before submitting a task does not avoid the race: the executor can shut down **between** the two statements. The submission path must handle rejection.

## 19. Handling Exceptions with `exceptionally`, `handle`, and `whenComplete`

Failures can be observed or recovered from **within the pipeline**:

```java
CompletableFuture<Integer> recovered =
        CompletableFuture.supplyAsync(() -> loadValue(), executor)
                .exceptionally(error -> {
                    report(error);
                    return 0;
                });
```

This is an illustrative snippet; `loadValue` and `report` are application helpers. `exceptionally` can **turn an exceptional completion into a default value**. Only do this if `0` is genuinely valid in business terms; otherwise, hiding the error can produce wrong results.

`handle((value,error) -> ...)` is invoked whether the source future completes normally or exceptionally, producing a new outcome. `whenComplete((value,error) -> ...)` is primarily for **observation**, typically preserving the original result/exception unless the callback itself throws an error.

### Pattern for preserving the cause

```java
CompletableFuture<Integer> checked =
        CompletableFuture.supplyAsync(() -> parse(), executor)
                .whenComplete((value, error) -> {
                    if (error != null) {
                        logger.error("parse failed", error);
                    }
                });
```

This is **logging integration pseudocode**, requiring `parse` and `logger` to be declared. Do not assume `error` is always the direct business exception; it may be a `CompletionException` or another wrapper. When finding the root cause, traverse `getCause()` and preserve the full stack trace, not just a message.

### Do not automatically retry every error

A `Supplier` may have already performed **partial side effects** before throwing an error: writing to a database, sending a request, or updating state. Retrying without idempotency or transactions can cause duplicate execution. `CompletableFuture` only records the computation's outcome; it does not roll back external systems.

## 20. `get()`, `join()`, Timeouts, and How to Wait

Both `get()` and `join()` allow retrieving the result after the future completes, but they have different exception contracts:

| API | On success | When task fails | When caller is interrupted | When future is cancelled |
| --- | --- | --- | --- | --- |
| `get()` | Returns `T` | `ExecutionException` | `InterruptedException` | `CancellationException` |
| `join()` | Returns `T` | Usually `CompletionException` | Does not declare checked interrupt | `CancellationException` |
| `get(timeout, unit)` | Returns `T` | `ExecutionException` | `InterruptedException` | `CancellationException`; may throw `TimeoutException` if not done |

**`get(timeout)` timing out does not automatically call `cancel(true)`.** The future may continue running even after the caller stops waiting.

`join()` does not accept a timeout in Java 17. You can enforce a deadline using `get(timeout, unit)` or design a pipeline with timeouts via `orTimeout`/`completeOnTimeout` depending on requirements.

Do not use `Thread.sleep(100)` and guess the task is done; it only sleeps for a duration and does not synchronize on the completion condition.

### Example 8: timeout while the task is waiting, then completing later

Create the file `CompletableTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "complete";
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(e);
                        }
                    }, executor);

            started.await();
            try {
                future.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("timed out");
            }

            System.out.println("cancelled=" + future.isCancelled());
            release.countDown();
            System.out.println("later=" + future.join());
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac CompletableTimeoutDemo.java
java CompletableTimeoutDemo
```

Output when there is no unexpected interrupt:

```text
timed out
cancelled=false
later=complete
```

The task cannot complete while `release` is still closed, so the first wait **must time out**. `get(30ms)` does not auto-cancel; after `main` releases the latch, the `Supplier` returns the result and `join()` retrieves it.

The example intentionally waits without a deadline on the final call to prove that a timeout is not cancellation. In a real API with an end-to-end SLA, you must use the remaining time or stop waiting according to policy.

## 21. `CompletableFuture.cancel(true)` Does Not Guarantee Task Interruption

This is an important pitfall. `CompletableFuture.cancel(boolean mayInterruptIfRunning)` is not like always controlling a `FutureTask` running in a `ThreadPoolExecutor`. According to `CompletableFuture`'s contract, the `mayInterruptIfRunning` parameter **has no effect in controlling execution via interruption in this implementation**.

Consequences:

- `future.cancel(true)` can transition the `CompletableFuture` to a cancelled/exceptional completion state.
- **There is no guarantee that the `Supplier`/`Runnable` actually stops running** if it has already started.
- It is possible for the future to be cancelled while the task is still performing side effects or cleanup.
- Dependent stages may receive a failed/cancelled completion status per contract, but that does not mean all in-flight actions have been stopped.
- If real stopping is needed, you must use a **cooperative cancellation mechanism**: a token, an `AtomicBoolean` flag, I/O timeouts, checking interrupted status when the code has an interrupt path, or task/executor ownership with a clear protocol.

**Do not state that `cancel(true)` always interrupts the worker running `supplyAsync`.** That is not guaranteed by `CompletableFuture`.

One way to illustrate the idea: the `Supplier` reads an `AtomicBoolean stopRequested` at safe points, and the caller sets the flag when the request expires. Ensure you do not stop midway through multi-field updates if doing so would break invariants, and do not leak resources on exit.

## 22. Controlling Threads and Avoiding Deadlocks from Blocking

Suppose an executor has only one worker:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> inner =
                    CompletableFuture.supplyAsync(() -> 42, executor);
            return inner.join();
        }, executor);
```

This is a **counterexample**. The single worker is running `outer` while blocking on `inner.join()`. `inner` also needs that very same worker to run. With no other worker available, the workflow can hit a **thread-starvation deadlock**.

Do not run this counterexample in a simple test without appropriate cancellation and timeout mechanisms. One fix is **composition instead of blocking**:

```java
CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> "start", executor)
                .thenCompose(ignored ->
                        CompletableFuture.supplyAsync(() -> 42, executor));
```

This is an illustrative snippet. `thenCompose` creates a dependency but **does not force the first worker to hold a running task while blocking on the second task**. The first stage completes, and then the next stage is submitted; the worker can process new work after the first stage finishes.

However, executor selection and callback design still matter: if a callback itself blocks for a long time, or if there is a dependency cycle between futures, deadlock can still occur.

## 23. Blocking I/O: Should `supplyAsync` Be Used with the Common Pool?

This code snippet:

```java
CompletableFuture<String> data =
        CompletableFuture.supplyAsync(() -> blockingRead());
```

does not turn `blockingRead()` into **non-blocking I/O**. It merely offloads the blocking call onto a thread in the default executor. While the I/O blocks, the worker can still be held up.

When there are many requests or long-blocking I/O, consider:

- Passing a **dedicated executor** sized and managed for the workload.
- Limiting concurrent requests and queue/backpressure.
- Setting **connect/read/request timeouts** on the actual I/O API.
- Using asynchronous I/O APIs if the domain and libraries support them.
- Collecting metrics on queues, threads, latency, rejections, and timeouts.
- Not submitting hundreds of thousands of blocking `Supplier`s to the common pool without control.

For short, independent CPU-bound tasks, the common pool may be reasonable. There is no rule that "every `supplyAsync` must use a separate pool", but **executor policy must match the workload type**, not just the lambda syntax.

### `runAsync` can also block

`runAsync(() -> sendEmail())` can still block if `sendEmail()` performs synchronous network I/O. Not returning a value does not help the worker free itself while I/O is waiting.

## 24. Safety of Shared Data and Happens-Before

A `CompletableFuture` completing does not automatically make every object touched by the `Supplier`/`Runnable` thread-safe.

Dangerous example:

```java
List<String> results = new ArrayList<>();

CompletableFuture<Void> a =
        CompletableFuture.runAsync(() -> results.add("A"));
CompletableFuture<Void> b =
        CompletableFuture.runAsync(() -> results.add("B"));
```

This is a **counterexample**, because two `Runnable`s can modify **the same `ArrayList`** without synchronization, causing a data race/corruption. Having the caller wait for both `a.join()` and `b.join()` **at the end** does not fix the race that already happened between the two writers.

Correct approaches:

- Each `Supplier` returns an **independent value**, then combines them when the futures complete.
- Use concurrent collections or locks if shared mutable state is genuinely needed.
- Organize a single owner to update the result.
- Publish immutable DTOs/results instead of mutating a shared list from multiple workers.

### Example 9: combining results of two `Supplier`s without sharing mutable variables

Create the file `CombineIndependentResultsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CombineIndependentResultsDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> left =
                    CompletableFuture.supplyAsync(() -> 20, executor);

            CompletableFuture<Integer> right =
                    CompletableFuture.supplyAsync(() -> 22, executor);

            CompletableFuture<Integer> total =
                    left.thenCombine(right, Integer::sum);

            System.out.println("total=" + total.join());
            System.out.println("left=" + left.join());
            System.out.println("right=" + right.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac CombineIndependentResultsDemo.java
java CombineIndependentResultsDemo
```

Output:

```text
total=42
left=20
right=22
```

The two sources produce separate immutable values. `thenCombine` runs only when both have completed normally and combines the two values into a new future. There is no need for a shared `static int sum` or `ArrayList` to collect results.

Regarding memory visibility: `Future.get()` and `CompletableFuture`'s completion mechanism provide synchronization relationships for the caller to read the published result. However, if workers continue modifying mutable objects outside the protocol, appropriate Java Memory Model principles must be applied.

## 25. `thenApply`, `thenApplyAsync`, `thenCompose`, and the Three Factory Methods

It is easy to confuse `supplyAsync` with every API containing "Async". Let's distinguish them clearly:

- `completedFuture(v)`: **source with an already-available result**.
- `supplyAsync(supplier)`: **new asynchronous source**, with a value produced by a `Supplier`.
- `runAsync(runnable)`: **new asynchronous source**, with no useful value.
- `thenApply(fn)`: transforms the result **of an existing stage**, potentially running inline on a relevant thread.
- `thenApplyAsync(fn, executor)`: transforms the previous stage's result, but **schedules the callback** via an executor.
- `thenCompose(fn)`: callback returns a `CompletionStage<U>` to **flatten** a subsequent async computation.
- `thenCombine(other, fn)`: combines two independent futures when both complete normally.

Example when a step returns a future:

```java
CompletableFuture<CompletableFuture<Integer>> nested =
        CompletableFuture.completedFuture(1)
                .thenApply(value ->
                        CompletableFuture.supplyAsync(() -> value + 1));
```

If you want `CompletableFuture<Integer>` instead of a future nested inside a future:

```java
CompletableFuture<Integer> flat =
        CompletableFuture.completedFuture(1)
                .thenCompose(value ->
                        CompletableFuture.supplyAsync(() -> value + 1));
```

These are illustrative snippets. `thenCompose` is used properly when the transformation function **itself returns a `CompletionStage`**, not for pure addition.

**Not every step needs to be async.** `thenApply(x -> x + 1)` allows lightweight inline processing without the task-submission overhead just to add a number.

## 26. Does an Async Continuation Always Run on the `Supplier`'s Thread?

No. For continuations **without the `Async` suffix**:

- If the source stage is **already completed** when the callback is registered, the callback may run immediately on the registering thread.
- If the source stage completes after registration, the callback may be run by the thread completing the stage or a thread participating in completion per implementation policy.
- You should not write correctness logic that depends on thread names or the number of context switches.

With `thenApplyAsync(fn, executor)`, the callback is scheduled using the specified executor (which may be rejected if the executor is shut down). However, an `Executor` can have an inline-execution policy, such as `Runnable::run`, so `Async` in the API refers to **how it is submitted through an executor**, not an absolute guarantee of "always a different thread from the caller".

### `ThreadLocal` and context

Because callbacks may run on different threads, `ThreadLocal` data of the calling thread is **not automatically propagated** across `CompletableFuture` stages. If you need a correlation ID, security context, or request metadata, you must **pass it explicitly** in the data or use a controlled context propagation mechanism.

In particular, a `ThreadLocal` set on a pooled worker can **persist across tasks** if `remove()` is not called in `finally`. You must manage cleanup rather than relying on `CompletableFuture` to clear `ThreadLocal` for you.

## 27. Submitting Multiple Tasks and Waiting Overall with `allOf()`

Example of independent `Supplier`s:

```java
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> "A", executor);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "B", executor);

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
all.join();

String combined = a.join() + b.join();
```

This is an illustrative snippet with a valid `executor`. `allOf` returns a `CompletableFuture<Void>` signaling when all input stages have finished. It does not pre-collect results into a `List<T>`; to obtain the values, the caller still reads the individual futures after overall success.

If one input future fails, `allOf` can complete exceptionally. **Do not assume `allOf` automatically cancels all remaining tasks or rolls back side effects.** It only establishes a completion relationship; stopping/retry/cleanup policies belong to the application layer.

`anyOf` completes when any one input future completes (normally or exceptionally); it has type `CompletableFuture<Object>` when using the general overload. Do not assume `anyOf` picks the "first successful result" as an optimal failover mechanism.

## 28. Distinguishing `completedFuture`, `failedFuture`, and `new CompletableFuture<>()`

These three ways of creating a future differ:

```java
CompletableFuture<String> success =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> failure =
        CompletableFuture.failedFuture(
                new IllegalStateException("failed"));

CompletableFuture<String> pending =
        new CompletableFuture<>();
```

- `success`: already completed **normally**.
- `failure`: already completed **exceptionally**; `join()` may throw `CompletionException`.
- `pending`: **incomplete**; another thread/callback must call `complete(value)`, `completeExceptionally(error)`, or `cancel(...)`.

`new CompletableFuture<>()` does not schedule any task on its own. If nobody completes it, `join()` can wait indefinitely.

A common mistake is using `new CompletableFuture<>()` instead of `supplyAsync` and then forgetting to write the corresponding completion code. When there is source work to run, using an async factory or a managed callback is clearer.

## 29. Observing Results Without Blocking the Caller Thread

If the goal is to continue processing when a result becomes available **without blocking the current thread**, use stage completion rather than calling `join()` too early:

```java
CompletableFuture<Integer> loaded =
        CompletableFuture.supplyAsync(() -> load(), executor);

CompletableFuture<Void> reported =
        loaded.thenAccept(value -> report(value));
```

This is an illustrative snippet; `load`, `report`, and `executor` are application-defined. `thenAccept` creates a stage that completes when the callback successfully consumes the value. There is no need to block the caller right in the middle of the pipeline.

**However:** if the application leaves scope, shuts down the executor, or the process exits before the stage finishes, the task may not have completed as required by business logic. There must be a **pipeline owner** that decides when to wait/aggregate/cancel and close resources.

If you need to be notified on completion, you can keep the Future and log the outcome with `whenComplete`; if you need to bound latency, configure a deadline and ensure cleanup. Not calling `join()` immediately does not mean errors are ignored or the workflow manages itself.

## 30. Completing Work and Shutting Down Executors Orderly

An application typically wants to:

1. Create/obtain an executor with an appropriate scope.
2. Submit initial tasks using `supplyAsync`/`runAsync`.
3. Build **the entire dependent pipeline** before starting to shut down the executor.
4. Wait for the **final future** or a set of outcomes with a deadline if needed.
5. Handle exceptional completion, cancellation, and retry/recovery.
6. If **you own the executor yourself**, request shutdown and wait for bounded termination.

A helper for JDK 17:

```java
static boolean stopExecutor(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown();

    if (executor.awaitTermination(5, TimeUnit.SECONDS)) {
        return true;
    }

    executor.shutdownNow();

    return executor.awaitTermination(5, TimeUnit.SECONDS);
}
```

This is an illustrative snippet inside a class with appropriate imports. It shuts down in two phases, preferring graceful shutdown first and then attempting to cancel remaining tasks. `shutdownNow()` does not guarantee stopping threads immediately; if the final step returns false, the lifecycle has not confirmed termination.

### Pitfall: shutting down the executor before dependent stages are scheduled

Example:

```java
CompletableFuture<Integer> first =
        CompletableFuture.supplyAsync(() -> 1, executor);

CompletableFuture<Integer> second =
        first.thenApplyAsync(value -> value + 1, executor);

executor.shutdown(); // May be too early for dependent stage.
```

This is a **counterexample**. Stage `second` may need to call the executor to schedule **after `first` completes**. If the executor is already shut down, it may reject that stage, leading to an exceptional completion related to rejection. Do not equate "submitted the source task" with "every future dependent task has already been accepted by the executor".

A more controllable pattern is to build/wait for final pipelines before shutting down, or use a lifecycle coordinator that knows precisely which dependent stages still need to be submitted later.

## 31. Shared Timeout Across Multiple Futures

A latency bug: calling `first.get(1, SECONDS)`, then `second.get(1, SECONDS)`, then `third.get(1, SECONDS)`, while thinking the total wait time is bounded to 1 second. In reality, it can wait nearly 3 seconds plus overhead.

If there is an end-to-end budget, use `System.nanoTime()` to measure elapsed time and compute **remaining** right before each `get(timeout, TimeUnit.NANOSECONDS)`:

```java
long started = System.nanoTime();
long budget = TimeUnit.SECONDS.toNanos(1);

long remaining1 = Math.max(
        0L, budget - (System.nanoTime() - started));
T1 firstValue = first.get(remaining1, TimeUnit.NANOSECONDS);

long remaining2 = Math.max(
        0L, budget - (System.nanoTime() - started));
T2 secondValue = second.get(remaining2, TimeUnit.NANOSECONDS);
```

This is **generic pseudocode** (`T1`, `T2`, and the futures must have concrete types). If the budget expires, respond with a timeout per contract rather than reusing the full initial timeout.

`System.nanoTime()` is an elapsed-time clock within the JVM; it is not a Unix timestamp. Do not use `System.currentTimeMillis()` as a monotonic deadline if the wall clock can be adjusted.

`get(timeout)` limits **the wait time**, not task cancellation; if a request exceeds its SLA, cancellation policy and side-effect handling must be designed separately.

## 32. Testing CompletableFuture Reliably

### Do not assert that an async future is always not done

A very fast task can finish before the caller reads `isDone()`. Use `CountDownLatch` like `AsyncStateLifecycleDemo` to hold the task at a deterministic point.

### Do not use `Thread.sleep` to wait for results

Use `join()`/`get()` when a test needs to confirm completion, along with a timeout larger than scheduler jitter if the test has a deadline. When using a latch, always have a path to release the latch in `finally` so the test does not leak workers if an exception occurs.

### Check both outcomes

Do not only assert the success value; for failures, inspect the wrapper/cause of `join`/`get`. With `runAsync`, verify that the action actually completed, not just that a Future of type `Void` exists.

### Shut down test executors properly

If a test creates its own `ExecutorService`, shut it down in `finally`, wait with a bound, and report an error if it still has not terminated. Do not "fix" thread leaks by making all threads daemons: daemon threads can allow the JVM to exit before resources/side effects finish.

### Avoid asserting common pool thread names

`CompletableFuture.supplyAsync(() -> Thread.currentThread().getName())` has no guaranteed thread name. To test executor selection, use a test-controlled `ThreadFactory` like `NamedExecutorDemo`.

### Check for shared state risks

If two tasks modify the same `ArrayList` or mutable structure, reading results via `join` at the end does not eliminate the data race. Use immutable results or proper concurrency primitives.

## 33. Common Mistakes

### 33.1. Thinking `completedFuture` runs a task asynchronously

Wrong. It creates a Future already completed normally with an existing value. It does not submit a `Supplier`/`Runnable` to a worker.

### 33.2. Thinking `supplyAsync` always returns before the task finishes

Not guaranteed. A very fast `Supplier` can finish before the method returns; do not assert `!isDone()` right after the factory call.

### 33.3. Using `runAsync` and trying to extract a business-typed value from `join()`

`CompletableFuture<Void>` completes normally with `null`. If you need a real value, use `supplyAsync`.

### 33.4. Assuming all downstream callbacks run on the same worker

`thenApply` does not guarantee affinity; `thenApplyAsync` specifies scheduling via an executor (if passed). Do not rely on `ThreadLocal` or thread names outside the contract.

### 33.5. Using the common pool for uncontrolled blocking I/O

It can hold workers for a long time and affect other tasks; choose an appropriate executor, timeout, and concurrency limit.

### 33.6. Creating a new executor per call and not shutting it down

It can cause threads/resources to grow unboundedly per request. Define pool ownership and lifecycle.

### 33.7. Discarding the Future for "fire-and-forget"

Exceptions from `Runnable`/`Supplier` may only be recorded in the `CompletableFuture`'s outcome. If nobody observes it, failures are missed from the application's perspective.

### 33.8. Catching `CompletionException` but ignoring the cause

The main error information is usually in `getCause()`; log the full throwable/cause chain when diagnostics are needed.

### 33.9. Confusing `get(timeout)` with cancel

A timeout only ends **the caller's wait**; the task may continue. Cancellation must follow its own policy.

### 33.10. Thinking `CompletableFuture.cancel(true)` definitely interrupts the `Supplier`

No. For `CompletableFuture`, `mayInterruptIfRunning` does not control execution via interruption by contract; use cooperative cancellation when needed.

### 33.11. Shutting down the executor while the pipeline still has unsubmitted dependent stages

Dependent `...Async(..., executor)` stages may be rejected after shutdown. Wait for final stages or coordinate the lifecycle properly.

### 33.12. Calling `join()` of a child task on the executor's only worker

It can cause a thread-starvation deadlock. Prefer composition over blocking.

### 33.13. Returning a mutable object and letting multiple threads mutate it

`CompletableFuture` publishes an outcome; it does not make a mutable object thread-safe. Use immutable DTOs or proper synchronization.

### 33.14. Ignoring errors of a dependent stage

The source future succeeding does not mean subsequent `thenApply`/`thenAccept`/`thenCompose` stages succeed. Observe the **final future** or all necessary outcomes.

### 33.15. Using a default fallback without considering business semantics

`exceptionally(error -> 0)` can mask a serious error. Only recover when the fallback is genuinely valid.

### 33.16. Confusing an action finishing with a side effect being committed

`runAsync` succeeding means the `Runnable` returned normally; if internal I/O/transactions have their own semantics, you must ensure durable success according to the business contract.

## 34. API Selection Checklist

Before writing an asynchronous operation, ask yourself:

1. **Already have the value immediately?** → `completedFuture(value)`.
2. **Have work to run that returns data?** → `supplyAsync(supplier[, executor])`.
3. **Have work to run and only care about completion/failure?** → `runAsync(runnable[, executor])`.
4. **Does the result need transformation?** → `thenApply` or `thenApplyAsync`.
5. **Does the next step itself return a `CompletionStage`?** → `thenCompose` to flatten.
6. **Two independent computations to combine?** → `thenCombine` or `allOf` depending on the result type.
7. **Does the task have blocking I/O, CPU-heavy work, or side effects?** → choose the executor and timeout accordingly.
8. **Who owns the Future?** → where will results/errors, timeouts, and cancellation be observed?
9. **Who owns the executor?** → where will it be shut down while ensuring no dependent stages still need to be scheduled?
10. **Is there shared mutable state?** → use immutable results, synchronization, or clear ownership.
11. **Is there a total deadline requirement?** → do not reset the timeout at each step.
12. **What if the task fails or is cancelled?** → how will propagation, logging, retry, recovery, and cleanup work?

A right choice should be based on **task semantics**, not just the shortest API signature.

## 35. Practice Exercises

**Exercise 1: cache hit / cache miss.** Build a method returning `CompletableFuture<String>`. If the `Map` has the key, use `completedFuture`; otherwise, use `supplyAsync` with an appropriate executor. Do not mistake `containsKey` followed by `get` for an atomic transaction if the `Map` is being modified.

**Exercise 2: summing two computations.** Use two `supplyAsync` calls returning `20` and `22`. Combine them with `thenCombine(Integer::sum)`. Assert `42` without relying on worker ordering.

**Exercise 3: an action without a result.** Use `runAsync` with an `AtomicInteger` incremented once; call `join()`, verify `Void` returns `null` and the counter equals 1.

**Exercise 4: testing lifecycle.** Use `CountDownLatch` to make the `Supplier` wait. Verify `isDone()==false` before release and true after `join()`.

**Exercise 5: rejection.** Create a single-thread executor, shut it down, then call `runAsync(..., executor)`. Verify `RejectedExecutionException` is handled at **task submission time**.

**Exercise 6: cooperative cancellation.** Inside a CPU-bound `Supplier`, read an `AtomicBoolean` token at safe points. The caller sets the token after a deadline; observe when the task actually stops and distinguish it from `CompletableFuture`'s cancelled state.

**Exercise 7: chaining stages.** Start from `completedFuture(10)`, `thenApply` multiply by 2, `thenApplyAsync` add 5 on a custom executor. Assert `25`, without asserting the callback ran on a fixed worker name unless you control the `ThreadFactory`.

**Exercise 8: non-blocking on the same executor.** Try `thenCompose` composition for a child task on a single-thread executor, contrasting it with the `inner.join()` counterexample that risks deadlock.

## 36. Self-Check Questions

**Question 1.** Does `CompletableFuture.completedFuture(42)` start a thread to compute 42?

**Answer:** No. It creates a `CompletableFuture` already completed normally with the value 42.

**Question 2.** Which functional interface does `supplyAsync` take, and what future type does it return?

**Answer:** It takes `Supplier<T>`; it returns `CompletableFuture<T>` completed with the value from `Supplier.get()`.

**Question 3.** What does `runAsync` take, and what kind of future does it return?

**Answer:** It takes `Runnable`; it returns `CompletableFuture<Void>`. On success, `join()` returns `null`.

**Question 4.** Why can't you assert `!future.isDone()` right after `supplyAsync(() -> 1)`?

**Answer:** A very fast task can complete before the caller checks; ordering depends on scheduling.

**Question 5.** When no executor is passed, what do `supplyAsync`/`runAsync` usually use?

**Answer:** By default they usually use `ForkJoinPool.commonPool()`, with a fallback to creating a new thread under specific parallelism conditions per the `CompletableFuture` contract.

**Question 6.** If you need control over worker names and shutdown, which overload should you use?

**Answer:** `supplyAsync(supplier, executor)` or `runAsync(runnable, executor)` with an executor managed by the owning component.

**Question 7.** Is `completedFuture(null)` an incomplete future?

**Answer:** No. It has already completed normally with a `null` result; `isDone()` is true.

**Question 8.** A `Supplier` throws `IllegalArgumentException`; what does `future.join()` usually report?

**Answer:** It usually throws `CompletionException`, with `getCause()` being `IllegalArgumentException`.

**Question 9.** When using `future.get()` on a failed task, what is the usual checked wrapper?

**Answer:** `ExecutionException`; inspect `getCause()` to retrieve the task's error.

**Question 10.** Does `future.get(100, MILLISECONDS)` timing out automatically cancel the task?

**Answer:** No. It only limits the caller's wait time, unless the application explicitly applies a cancellation policy.

**Question 11.** Does `CompletableFuture.cancel(true)` guarantee interrupting the thread running the `Supplier`?

**Answer:** No. `mayInterruptIfRunning` is not used to control execution via interruption in `CompletableFuture`.

**Question 12.** If the source future is already completed, must `thenApply` run on a worker?

**Answer:** No. The callback may run on the registering thread, so do not use it to guarantee background execution.

**Question 13.** Why use `thenCompose` when a callback returns a `CompletableFuture`?

**Answer:** To flatten the stages, avoiding a nested `CompletableFuture<CompletableFuture<T>>` type.

**Question 14.** Two `Supplier`s write concurrently to the same `ArrayList`; is just waiting on `allOf` enough for thread safety?

**Answer:** No. Waiting after the tasks finish does not fix the race between the two writers. Proper data structures or synchronization protocols are required.

**Question 15.** What can happen if you call `shutdown` on the executor after submitting the source task but before a dependent `thenApplyAsync` is ready?

**Answer:** The dependent stage may be rejected by the executor when it needs to be scheduled, leading to exceptional completion; you must coordinate the lifecycle of the entire pipeline.

**Question 16.** Why should executors be managed at service scope instead of creating a new one per request?

**Answer:** To control worker count, queue/backpressure, reuse, and shutdown, avoiding thread/resource leaks.

**Question 17.** When should you use `runAsync` instead of `supplyAsync`?

**Answer:** When the work has no useful return data and you only need to know whether it completed or failed; if there is a business result, use `Supplier`.

**Question 18.** Does using `completedFuture(mutableObject)` automatically deep-copy the object?

**Answer:** No. The future holds a reference; an immutable snapshot or synchronization is needed if the object is used across threads.

## 37. Summary

The three factory methods of `CompletableFuture` address three different needs:

- **`completedFuture(value)`**: you already have a value, creating a future that is **already completed normally** right away, without running a background task.
- **`supplyAsync(supplier[, executor])`**: you need to **execute work that produces a result**; the future completes with the value returned by the `Supplier` or the error thrown by the `Supplier`.
- **`runAsync(runnable[, executor])`**: you need to **execute work with no return value**; the `Void` future completes normally with `null` or completes exceptionally if the `Runnable` fails.

Async operations do not guarantee that `isDone` is definitely false when the factory returns, do not guarantee a specific thread name, and do not automatically make shared mutable state safe. Omitting the executor usually uses the common pool; for blocking workloads or specific lifecycles, use an application-owned executor and manage its shutdown.

When writing applications, keep the Future and inspect the outcome via `join`/`get` or error-handling pipelines, distinguish `CompletionException` / `ExecutionException` / timeout / cancellation, use composition to avoid blocking workers in the same executor, and design deadlines as well as cooperative cancellation. **`CompletableFuture` is a tool for organizing the completion flow of work; correctness still depends on the executor, the data, and the business protocol.**
