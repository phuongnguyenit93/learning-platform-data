# thenAcceptBoth() and runAfterBoth(): Coordinating Two Branches Without a Return Value

In Java Concurrency, `CompletableFuture` and `CompletionStage` do more than just receive an asynchronous result: they also allow you to describe **dependencies between multiple tasks**. When two branches can run independently, but the next step is only allowed to execute **after both succeed**, two particularly useful methods are:

- **`thenAcceptBoth(other, action)`**: waits for **both stages to complete normally**, then invokes a `BiConsumer` **receiving the results of both**, performs an action, and **returns no business value**.
- **`runAfterBoth(other, action)`**: also waits for **both stages to complete normally**, but invokes a `Runnable` **receiving neither stage's result**, performs an action, and **returns no business value**.

Both produce a **dependent stage of type `CompletionStage<Void>`**; when called on `CompletableFuture`, the concrete return type is typically **`CompletableFuture<Void>`**. `Void` does not mean "fire-and-forget": the new stage still carries **completion, error, and cancellation states**, and can be tracked, combined, or intentionally awaited.

**Core idea:** use `thenAcceptBoth` when the action needs **both input values**, and `runAfterBoth` when you only need **both sides to complete successfully before running**. Neither method automatically starts the two source tasks, turns code parallel on its own, or handles errors or cancellation for the entire pipeline.

This article applies to **Java 17+ in general Java concurrency**, with standalone examples runnable via `javac`/`java` and no external framework dependencies.

## 1. Why Coordinate Two Branches?

A request might require two independent tasks:

```text
                        Start request
                              |
                    +---------+----------+
                    |                    |
               Branch A             Branch B
             read config          verify data
                    |                    |
                    v                    v
             A completes          B completes
                    \                    /
                     \                  /
                       Both succeeded?
                              |
                              v
                        Final action
                       notify / log
                              |
                              v
                    CompletionStage<Void>
```

If you only use `Future.get()`, one thread may have to wait for A, then wait for B, and only then perform the action:

```java
A a = futureA.get();
B b = futureB.get();
notify(a, b);
```

This is **pseudocode using Java syntax**; types `A`, `B`, and method `notify` are not defined. The two `get()` calls can block the **orchestrating thread** if the results are not yet ready.

With `CompletionStage`, we can declare the dependency **up front**:

```java
CompletionStage<Void> notification =
        stageA.thenAcceptBoth(stageB, (a, b) -> notify(a, b));
```

This is an excerpt: `stageA` and `stageB` are two `CompletionStage` instances of compatible types; `notify` is an application-defined action. Calling `thenAcceptBoth` registers a dependent stage; it does not force the caller to block waiting for both stages at registration time.

If the notification needs to run on a different executor, use the `thenAcceptBothAsync` overload with an explicitly chosen `Executor`, rather than blocking the incoming thread to wait.

## 2. Distinguish "No Return Value" from "No Completion"

With `thenAcceptBoth` and `runAfterBoth`, the callback is an **action returning `void`**, yet the method still **returns a new stage** to track that action:

```java
CompletableFuture<Void> afterBoth =
        first.thenAcceptBoth(second, (a, b) -> {
            System.out.println(a + " / " + b);
        });

// At a boundary where waiting is permitted:
afterBoth.join();
```

This is an excerpt; `first` and `second` are already-defined `CompletableFuture` instances. A successful `join()` returns `null` for type `Void`, but the most useful guarantee is that **after `join()`, the dependent stage's action has completed according to its contract**.

A `CompletableFuture<Void>` can:

1. Complete **successfully**: the callback has finished running, and the `Void` result is normally `null`.
2. Complete **exceptionally**: an input failed/was canceled or the callback threw an error; `join()` may throw `CompletionException` or `CancellationException` depending on the outcome.
3. Be incomplete: the trigger condition has not been met yet, or the callback is still running / has not yet been executed by the scheduler.
4. Be canceled directly: the stage state transitions to canceled if `cancel` wins the terminal-completion race; this **does not automatically guarantee stopping an already-running callback**.

**Do not discard the handle** just because the callback returns `void` if an action such as mandatory logging, sending notifications, or updating an audit log must be confirmed and monitored for errors.

## 3. API Signatures of thenAcceptBoth() and runAfterBoth()

Two key signatures on `CompletionStage<T>` (shown with simplified generic names for readability):

```java
<U> CompletionStage<Void> thenAcceptBoth(
        CompletionStage<? extends U> other,
        BiConsumer<? super T, ? super U> action);

CompletionStage<Void> runAfterBoth(
        CompletionStage<?> other,
        Runnable action);
```

These are **illustrative API signatures**, not a complete class implementation. `thenAcceptBoth` takes a `BiConsumer<T, U>`: a callback with **two parameters** that returns `void`. `runAfterBoth` takes a `Runnable`: a callback with **no parameters** that returns `void`.

When called on `CompletableFuture<T>`, its overrides return `CompletableFuture<Void>`. The available variants are:

```java
first.thenAcceptBoth(second, (a, b) -> use(a, b));
first.thenAcceptBothAsync(second, (a, b) -> use(a, b));
first.thenAcceptBothAsync(
        second, (a, b) -> use(a, b), executor);

first.runAfterBoth(second, () -> signalReady());
first.runAfterBothAsync(second, () -> signalReady());
first.runAfterBothAsync(
        second, () -> signalReady(), executor);
```

The lines above are **excerpts**; you must define the two stages, `executor`, `use`, and `signalReady`. `*Async` does not spawn a dedicated new thread for every callback; it requests execution using the implementation's default asynchronous execution facility or the specified `Executor`.

### Quick Comparison Table

| Criterion | `thenAcceptBoth` | `runAfterBoth` |
|---|---|---|
| Condition to invoke action | **Both stages complete normally**. | **Both stages complete normally**. |
| Callback | `BiConsumer<T,U>`. | `Runnable`. |
| Receives both stage values? | **Yes**, two typed parameters. | **No**. |
| Dependent stage result | `Void`. | `Void`. |
| Use when | You need both results to send a notification, log info, or produce a side effect. | You only need "both finished" before cleanup, signaling, or triggering an action. |
| If one source completes exceptionally | Normal action **does not run**; dependent stage completes exceptionally. | Same. |
| If callback throws an exception | Dependent stage completes exceptionally. | Same. |
| Runs both sources concurrently automatically? | **No**. | **No**. |
| Blocks the caller automatically? | **No** at registration time. | **No** at registration time. |
| Has Async and Executor overloads? | **Yes**. | **Yes**. |

## 4. Example 1 — Both Branches Succeed, One Action Uses Results and One Only Waits

This example uses two `completedFuture` instances so it does not depend on scheduling. `thenAcceptBoth` receives both `7` and `5` to build a string; `runAfterBoth` only records that both have completed. `main` waits for **both dependent stages** before printing.

Create **`BothBasicsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BothBasicsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> left =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> right =
                CompletableFuture.completedFuture(5);

        AtomicReference<String> description =
                new AtomicReference<>();
        AtomicBoolean barrierRan = new AtomicBoolean();

        CompletableFuture<Void> acceptsBoth =
                left.thenAcceptBoth(right, (a, b) -> {
                    description.set(a + " + " + b + " = " + (a + b));
                });

        CompletableFuture<Void> runsAfterBoth =
                left.runAfterBoth(right, () -> barrierRan.set(true));

        CompletableFuture.allOf(acceptsBoth, runsAfterBoth).join();

        System.out.println("thenAcceptBoth: " + description.get());
        System.out.println("runAfterBoth ran: " + barrierRan.get());
        System.out.println("Void result: " + acceptsBoth.join());
    }
}
```

Compile and run on JDK 17+:

```bash
javac BothBasicsDemo.java
java BothBasicsDemo
```

Output:

```text
thenAcceptBoth: 7 + 5 = 12
runAfterBoth ran: true
Void result: null
```

**Analysis:**

- `left` and `right` have already completed normally, so both actions are eligible to run.
- `thenAcceptBoth` uses both parameters to build the result string. `runAfterBoth` never sees `7` or `5`; it simply waits for both stages to succeed to set the flag.
- `CompletableFuture.allOf(...).join()` acts as a **barrier** waiting for both dependent actions to finish before `main` reads the two atomic variables.
- `acceptsBoth.join()` returns `null` because of the `Void` type, which does **not** mean the action did not run.
- **No execution order is guaranteed** between the two actions: they are independent, both depending on `left` and `right`. The program only prints in `main` after the barrier, so stdout is deterministic.

This is a semantics example and **does not demonstrate parallelism**, since the sources are already completed. When sources are backed by real asynchronous tasks, the API dependencies and behavior remain the same.

## 5. The "Both" Condition Means Both Stages Normally, Not "Either One"

An easily overlooked distinction:

```text
A = completed normally, B = still incomplete
                 |
                 v
thenAcceptBoth / runAfterBoth action HAS NOT RUN yet
                 |
        B completed normally
                 |
                 v
        action is eligible to run
                 |
                 v
       dependent stage completes
```

If either source completes **exceptionally**, the `thenAcceptBoth`/`runAfterBoth` action is **not executed on the success path**. The dependent stage will have an exceptional outcome according to the contract. Do not assume that if A fails, B is canceled or stopped: the inputs are separate stages.

Do not phrase this too rigidly as "waiting for A and B to return a value": a source can be a `CompletableFuture<Void>` that completes normally with `null`; `runAfterBoth` can still wait on it, and `thenAcceptBoth` can receive that `null` argument if the stage types permit.

`thenAcceptBoth` does **not** pick the "fastest result", and `runAfterBoth` is **not** equivalent to `runAfterEither`. If you only need **one** stage to complete normally to trigger an action, study `acceptEither`/`runAfterEither` with their own exception semantics; do not swap APIs just because their names look similar.

## 6. Example 2 — Proving One Completed Branch Does Not Complete the Dependent Stage

We create two incomplete `CompletableFuture` instances and call `complete` manually in a deterministic sequence. No `Thread.sleep()` or scheduler guesswork is needed.

Create **`BothCompletionGateDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BothCompletionGateDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();

        AtomicReference<String> captured = new AtomicReference<>();
        AtomicBoolean signalled = new AtomicBoolean();

        CompletableFuture<Void> accept = first.thenAcceptBoth(
                second, (a, b) -> captured.set(a + "+" + b));

        CompletableFuture<Void> run =
                first.runAfterBoth(second, () -> signalled.set(true));

        first.complete("A");

        System.out.println("Accept done after A: " + accept.isDone());
        System.out.println("Run done after A: " + run.isDone());

        second.complete("B");
        CompletableFuture.allOf(accept, run).join();

        System.out.println("Accept done after B: " + accept.isDone());
        System.out.println("Run done after B: " + run.isDone());
        System.out.println("Captured: " + captured.get());
        System.out.println("Signalled: " + signalled.get());
    }
}
```

```bash
javac BothCompletionGateDemo.java
java BothCompletionGateDemo
```

Output:

```text
Accept done after A: false
Run done after A: false
Accept done after B: true
Run done after B: true
Captured: A+B
Signalled: true
```

**Why?** When only `first` is completed, `second` has no outcome yet, so both dependent stages remain incomplete. Once `second.complete("B")` succeeds, the `both` condition is satisfied. The two callbacks do not necessarily run in `accept`-before-`run` order, but `allOf(...).join()` confirms both have finished before printing the variables.

### When and Where Does the Callback Run?

With **non-Async** `thenAcceptBoth`/`runAfterBoth`, the action may run on the thread completing the second source, another thread participating in completion, or even immediately during registration if both inputs are already completed. **There is no guarantee it always runs on `main` or on a dedicated worker.**

Therefore, if the action is heavy or performs blocking I/O, do not casually run it in the non-Async variant: it can occupy the source-completing thread and increase pipeline latency. Choose the Async overload with an appropriate executor.

## 7. thenAcceptBoth() Ignores a Return Value, Not the Input Values

A `BiConsumer<T, U>` still receives both **typed** results:

```java
CompletableFuture<User> user = loadUser();
CompletableFuture<Settings> settings = loadSettings();

CompletableFuture<Void> recorded =
        user.thenAcceptBoth(settings, (u, s) -> {
            audit(u.id(), s.version());
        });
```

This is an **excerpt** without definitions for `User`, `Settings`, `loadUser`, `loadSettings`, or `audit`; it is not a standalone program. It illustrates that no new value is returned from the action, yet both source values are still passed in.

Avoid doing this:

```java
user.runAfterBoth(settings, () -> {
    audit(user.join().id(), settings.join().version());
});
```

when the action needs both values: even though the sources have already completed when the action runs normally, calling `join()` inside to extract values makes the code verbose, less expressive in types, and more error-prone. `thenAcceptBoth` is specifically designed to receive both inputs.

**Note on capturing mutable state:** The two sources may run on different threads. If an action holds a reference to a mutable object and another thread continues modifying it concurrently, the stage's completion does not automatically make that object thread-safe for subsequent mutations. Prefer `record`, immutable snapshots, or clear synchronization/ownership.

## 8. runAfterBoth() Is a Value-Free Completion Barrier with an Action

A useful pattern:

```java
CompletableFuture<Void> waitBoth =
        saveA.runAfterBoth(saveB, () -> {
            System.out.println("Both saves completed");
        });
```

This is an excerpt assuming `saveA` and `saveB` are stages that can complete normally. The callback does not need to know their return values, so `Runnable` is sufficient.

Common use cases:

1. **Marking two preparation steps complete** and then releasing a waiting signal.
2. **Starting a final step** that does not need the two sources' values, such as updating a "ready" flag once both operations succeed.
3. **Coordinating ordered cleanup** when two operations complete normally and a follow-up step must run; you must separately define the error-handling path if a source fails or is canceled.
4. **Creating an observable endpoint**: the dependent `CompletableFuture<Void>` can be awaited with `join/get` or composed with other stages.

**Do not use `runAfterBoth` as a `finally` block.** If an input fails or is canceled, the normal callback **does not run**. Cleanup that must run regardless of success or failure may require `handle`, `whenComplete`, `allOf` with error handling, or `try/finally` directly inside the resource-owning task.

## 9. Comparing thenAcceptBoth / runAfterBoth with Other Combinators

| Method | Dependency | Callback Input | Output |
|---|---|---|---|
| `thenApply(fn)` | One stage succeeds. | One value `T`. | Stage with result `U`. |
| `thenAccept(action)` | One stage succeeds. | One value `T`. | `CompletionStage<Void>`. |
| `thenRun(action)` | One stage succeeds. | No value. | `CompletionStage<Void>`. |
| `thenCombine(other, fn)` | **Both stages succeed.** | Two values `T, U`. | Stage with result `V`. |
| **`thenAcceptBoth(other, action)`** | **Both stages succeed.** | Two values `T, U`. | **`CompletionStage<Void>`**. |
| **`runAfterBoth(other, action)`** | **Both stages succeed.** | No value. | **`CompletionStage<Void>`**. |
| `acceptEither(other, action)` | Per either-stage normal completion semantics. | One result from the chosen stage. | `CompletionStage<Void>`. |
| `runAfterEither(other, action)` | Per either-stage normal completion semantics. | No value. | `CompletionStage<Void>`. |
| `CompletableFuture.allOf(...)` | Set of multiple `CompletableFuture`s. | No built-in callback on `allOf` itself. | `CompletableFuture<Void>` barrier. |

`thenCombine` is the natural choice when you **need to return a combined value** to the next stage. `thenAcceptBoth` fits when the primary goal is to **consume both values** via an action. `runAfterBoth` fits when the action only requires completion and does not need to read either input.

`CompletableFuture.allOf(a, b)` creates a barrier for multiple Futures (not limited to two), but **does not automatically pass two results into a `BiConsumer`** like `thenAcceptBoth`. If each operation is already a `CompletableFuture<Void>`, `allOf` is also useful for waiting on a batch. You must still account for exception propagation and cancellation, and not treat `allOf` as structured cancellation.

## 10. Async Variants: Who Executes the Callback?

There are three forms:

```java
left.thenAcceptBoth(right, action);
left.thenAcceptBothAsync(right, action);
left.thenAcceptBothAsync(right, action, executor);
```

And correspondingly:

```java
left.runAfterBoth(right, runnable);
left.runAfterBothAsync(right, runnable);
left.runAfterBothAsync(right, runnable, executor);
```

These are excerpts requiring appropriately typed variables. The **both-condition semantics** remain identical across all three overloads; they differ in **action execution policy**:

- **Non-Async:** the action may run on the thread that completes a source, or on the thread attaching the dependent stage if both are already done. No fixed thread is guaranteed; it does not necessarily submit a new task to an executor.
- **Async without Executor:** the action is executed using the implementation's default asynchronous execution facility. For standard `CompletableFuture`, this is typically `ForkJoinPool.commonPool()` (with fallback behavior depending on configuration/parallelism).
- **Async with Executor:** the action is submitted to the **specified executor**, giving control over resources, isolation, and shutdown; code must still handle rejection and exceptions.

The `Async` suffix does not make the two sources run in parallel; the two sources must be started/completed on their own. Nor does it turn a **blocking I/O** callback into non-blocking code: if the callback makes a blocking network call, the executor worker running that action is still tied up.

### Avoiding Deadlock on Small Pools

Suppose `thenAcceptBothAsync(..., singleThreadExecutor)` is scheduled on the same single-worker executor where the current worker is calling `actionStage.join()`. If the dependent action can only run on that worker, blocking can cause **thread starvation/deadlock**. A better approach is to **return the dependent stage**, chain further via `thenRun`/`thenCompose`, and only call `join/get` at an outer boundary where waiting is permitted.

Do not assume that because two stages have two callbacks, the JVM will create two separate threads; the execution facility and scheduling determine that.

## 11. Example 3 — Two Async Branches Running on a Custom Executor

This program uses an `ExecutorService` owned by `main`, runs two independent `supplyAsync` sources, and attaches **two Async dependent actions** to the same executor. To avoid relying on worker numbering, each callback only records a boolean indicating whether the thread name has the prefix `both-worker-`. `main` prints only after both actions complete.

Create **`BothAsyncExecutorDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class BothAsyncExecutorDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger nextWorker = new AtomicInteger();

        ExecutorService executor = Executors.newFixedThreadPool(
                2, runnable -> {
                    Thread thread = new Thread(
                            runnable,
                            "both-worker-" + nextWorker.incrementAndGet()
                    );
                    return thread;
                }
        );

        AtomicInteger sum = new AtomicInteger();
        AtomicBoolean acceptOnPool = new AtomicBoolean();
        AtomicBoolean runOnPool = new AtomicBoolean();

        try {
            CompletableFuture<Integer> first =
                    CompletableFuture.supplyAsync(() -> 4, executor);
            CompletableFuture<Integer> second =
                    CompletableFuture.supplyAsync(() -> 6, executor);

            CompletableFuture<Void> accept =
                    first.thenAcceptBothAsync(second, (a, b) -> {
                        sum.set(a + b);
                        acceptOnPool.set(
                                Thread.currentThread().getName()
                                        .startsWith("both-worker-")
                        );
                    }, executor);

            CompletableFuture<Void> run =
                    first.runAfterBothAsync(second, () -> {
                        runOnPool.set(
                                Thread.currentThread().getName()
                                        .startsWith("both-worker-")
                        );
                    }, executor);

            CompletableFuture.allOf(accept, run).join();
            System.out.println("Combined: " + sum.get());
            System.out.println("Accept on executor: "
                    + acceptOnPool.get());
            System.out.println("Run on executor: " + runOnPool.get());
        } finally {
            executor.shutdown();
        }

        System.out.println("Executor terminated: "
                + executor.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

```bash
javac BothAsyncExecutorDemo.java
java BothAsyncExecutorDemo
```

Output when the executor operates normally:

```text
Combined: 10
Accept on executor: true
Run on executor: true
Executor terminated: true
```

**Analysis:**

1. The two `supplyAsync` calls submit two independent computations; the pool has two workers so they can run side by side, though true simultaneous execution at any instant is not guaranteed.
2. `thenAcceptBothAsync` is only submitted for execution once both results are available, and receives `a=4, b=6`.
3. `runAfterBothAsync` only needs both sources to complete normally and **is not passed `4` or `6`**.
4. Both callbacks are requested to run on the specified executor, so their thread names carry the prefix set by the thread factory. The program prints a **boolean**, not `both-worker-1` or `both-worker-2`, because exact worker assignment is not fixed.
5. `allOf(accept, run).join()` marks the point where both actions have finished; `main` shuts down the executor after observing completion. `awaitTermination()` verifies the executor lifecycle.

**Lesson scope:** this demonstrates executor selection for callbacks, not a benchmark proving `*Async` is always faster. For very lightweight actions, submission/scheduling overhead can exceed the computation itself; for blocking I/O actions, you must consider an appropriate pool and timeouts.

## 12. What If One of the Two Sources Fails?

`thenAcceptBoth` and `runAfterBoth` are **success-dependent combinators**. If one source completes exceptionally, the normal callback **is not run**, and the dependent stage also becomes exceptional per completion rules. There is no automatic mechanism to:

- Invoke the callback with `null` for the failed source.
- Retry the failed source.
- Cancel the other source.
- Roll back side effects already performed by a source.
- Pick a deterministic "preferred" exception when **both** fail.

A stage can fail because a supplier/callback throws an exception, `completeExceptionally` is called, a timeout occurs via `orTimeout`, or via cancellation. When inspecting `CompletionException` from `join()`, check `getCause()` to determine the underlying cause. If both fail, do not rely on scheduler ordering to guess which exception becomes the dependent stage's outcome.

### Example 4 — Failure Blocks the Action; Recover the Source and Coordinate Again

Create **`BothFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class BothFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> good =
                CompletableFuture.completedFuture(3);
        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("missing value")
                );

        AtomicBoolean acceptCalled = new AtomicBoolean();
        AtomicBoolean runCalled = new AtomicBoolean();

        CompletableFuture<Void> accept = good.thenAcceptBoth(
                failed, (a, b) -> acceptCalled.set(true));

        CompletableFuture<Void> run = good.runAfterBoth(
                failed, () -> runCalled.set(true));

        try {
            accept.join();
        } catch (CompletionException e) {
            System.out.println("Failure type: "
                    + e.getCause().getClass().getSimpleName());
        }

        System.out.println("Accept called: " + acceptCalled.get());
        System.out.println("Run called: " + runCalled.get());
        System.out.println("Run exceptional: "
                + run.isCompletedExceptionally());

        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> 7);
        AtomicInteger combined = new AtomicInteger();

        good.thenAcceptBoth(recovered,
                (a, b) -> combined.set(a + b)).join();

        System.out.println("Recovered sum: " + combined.get());
    }
}
```

```bash
javac BothFailureDemo.java
java BothFailureDemo
```

Output:

```text
Failure type: IllegalStateException
Accept called: false
Run called: false
Run exceptional: true
Recovered sum: 10
```

**Explanation:** `failedFuture` is already exceptional, so neither dependent action (`accept` or `run`) **runs**. `accept.join()` throws `CompletionException` with cause `IllegalStateException`. We use `failed.exceptionally(...)` to create a **new stage** with fallback `7`; when combined with `good=3`, `thenAcceptBoth` runs normally and sets the sum to `10`.

`run.isCompletedExceptionally()` being `true` does not mean the `run` callback ran and threw: rather, it failed because a source failed **before the `Runnable` was ever invoked**.

### Cancellation Path

When a source `CompletableFuture` is canceled via `cancel(true)`, that source itself may throw `CancellationException` on `join()`. A dependent stage requiring that source to succeed may receive an exceptional outcome wrapping the cancellation in `CompletionException`. `isDone()` being `true` does not mean success; `isCancelled()` on the dependent stage is not necessarily `true` even when the failure cause was a canceled source.

Canceling a stage does not automatically interrupt the underlying worker in the standard `CompletableFuture` implementation. In particular, **canceling `accept` does not automatically cancel upstream `good` and `failed`**; if real work must be stopped, you need an explicit cancellation policy/ownership model.

## 13. What Happens If the Action Throws an Error?

Both sources can succeed, yet the **final action** can still fail:

```java
CompletableFuture<Integer> a =
        CompletableFuture.completedFuture(2);
CompletableFuture<Integer> b =
        CompletableFuture.completedFuture(3);

CompletableFuture<Void> written = a.thenAcceptBoth(b, (x, y) -> {
    throw new IllegalStateException("audit unavailable");
});
```

This is an excerpt; `CompletableFuture` must be imported. Both sources succeed, but the dependent `written` completes **exceptionally** because the action throws. `written.join()` typically throws `CompletionException` wrapping `IllegalStateException`. Do not confuse "both branches succeeded" with "the follow-up action is guaranteed to succeed".

With `runAfterBoth`, a `Runnable` can also throw an unchecked exception. Both methods allow using `exceptionally`, `handle`, or `whenComplete` on the **dependent stage** to observe or recover from errors:

```java
CompletableFuture<Void> observed = written.whenComplete(
        (ignored, error) -> {
            if (error != null) {
                System.err.println("Audit failure: " + error);
            }
        });
```

This excerpt uses `written` from the previous example. `whenComplete` is for **observation**; it does not turn a failure into success just by logging it. For recovery, you can use `exceptionally(error -> null)` on `CompletableFuture<Void>`, but you must explicitly decide whether treating an audit failure as a "fallback success" makes business sense.

**A common mistake:** registering an action to write an audit log and then discarding the resulting `CompletableFuture<Void>`. If the action fails without a terminal observer/metrics, the error can remain trapped in the dependent stage without the caller ever noticing.

## 14. No Ordering Guarantee Between Two Independent Dependents

Consider two actions both waiting on the same A and B:

```java
CompletableFuture<Void> first =
        a.thenAcceptBoth(b, (x, y) -> audit(x, y));

CompletableFuture<Void> second =
        a.runAfterBoth(b, () -> publishReady());
```

This is an excerpt requiring `a`, `b`, and the two application methods. **There is no causal ordering** from `first` to `second` merely because the line creating `first` is written earlier. Once both sources complete, the two actions may execute in any order or on different threads.

If `publishReady()` **must run after the audit completes**, you must declare an explicit dependency:

```java
CompletableFuture<Void> audited =
        a.thenAcceptBoth(b, (x, y) -> audit(x, y));

CompletableFuture<Void> published =
        audited.thenRun(() -> publishReady());
```

Because `published` depends on `audited`, the publish action only runs normally after the audit stage succeeds. Similarly, you can chain `runAfterBoth` on a completed `Void` stage and another stage. This is fundamentally different from registering two independent actions on the same two sources.

### Example 5 — Enforcing Order via Dependencies, Not Registration Timing

Create **`OrderedBothActionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class OrderedBothActionsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> first =
                CompletableFuture.completedFuture(2);
        CompletableFuture<Integer> second =
                CompletableFuture.completedFuture(3);

        List<String> events = new ArrayList<>();

        CompletableFuture<Void> audited = first.thenAcceptBoth(
                second,
                (a, b) -> events.add("audit=" + (a + b))
        );

        CompletableFuture<Void> published = audited.thenRun(
                () -> events.add("published")
        );

        CompletableFuture<Void> finished =
                published.runAfterBoth(second,
                        () -> events.add("finished"));

        finished.join();
        System.out.println("Events: " + events);
        System.out.println("Finished normally: "
                + !finished.isCompletedExceptionally());
    }
}
```

```bash
javac OrderedBothActionsDemo.java
java OrderedBothActionsDemo
```

Output:

```text
Events: [audit=5, published, finished]
Finished normally: true
```

Here, the plain `ArrayList` is **not mutated concurrently by two independent callbacks**: the actions form a dependency chain `audited → published → finished`, and `main` only reads `events` after `finished.join()`. Even if individual actions are moved to different executors in an expanded design, the dependency chain still expresses the completion-based ordering between actions.

**Do not extend this pattern** by having multiple independent dependent actions mutate the same `ArrayList` and assuming `CompletableFuture` synchronizes the collection. If multiple writers are not chained sequentially, use concurrent data structures/synchronization or return immutable results from each branch.

## 15. "Both Succeed" Means the Callback Is Not a `finally` Block

Suppose each source uses a network connection or file:

```text
Task A ----- success ----+
                         +-- runAfterBoth(cleanup)
Task B ----- failure ----+
```

In this case, `runAfterBoth(cleanup)` is **not an always-run cleanup callback**: if B fails, the normal `Runnable` does not run. Therefore, for resources owned by task A or B, place `try-with-resources` or `finally` **inside the respective task itself**. For resources belonging to the whole operation, you can use a combined stage with `whenComplete` or a lifecycle mechanism that confirms the branches have ended per their contract.

**Do not mechanically replace it with `whenComplete`** if you need to wait for both tasks to actually stop. An exceptional/canceled outcome on a `CompletableFuture` can occur before the background computation stops. If a source is canceled in state while its worker is still running, a callback observing the Future's state is not proof that files or sockets have been closed.

One more point: `thenAcceptBoth` and `runAfterBoth` do not impose a completion order between A and B. `B` may finish before `A`, and the action runs after `A` also completes; if A and B perform competing side effects on the same resource, you must synchronize **inside the branches**, not wait until the final callback to deal with a data race.

## 16. Compared to `allOf()`: Choosing the Right Aggregation Level

For **exactly two stages** where the action needs both values, `thenAcceptBoth` is convenient and type-safe:

```java
CompletionStage<Void> sent =
        order.thenAcceptBoth(customer,
                (o, c) -> sendReceipt(o, c));
```

This is an illustrative excerpt. If you only wait for two stages to complete successfully and then run an action needing no inputs, `runAfterBoth` is concise:

```java
CompletionStage<Void> started =
        prepareA.runAfterBoth(prepareB, () -> startNextPhase());
```

For **N stages**, `CompletableFuture.allOf(stages...)` provides a more flexible barrier:

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(jobA, jobB, jobC);

CompletableFuture<Void> committed =
        all.thenRun(() -> markBatchDone());
```

These snippets assume the stages and business methods are already declared. `allOf` returns `CompletableFuture<Void>` and does not automatically produce a `List<T>` of the inputs. If you need the values after `allOf`, you can retrieve each result per contract after the barrier succeeds or build a transformation stage.

**Avoid concluding that "`allOf` waits for all threads/side effects unconditionally"** when an input is completed early by cancellation/timeout while its background worker is still running. Stage completion and worker termination are two distinct milestones. If any stage in the group fails, `allOf` completes exceptionally; it does not automatically cancel all siblings under a structured cancellation scope.

## 17. Difference from `thenCombine()`: Do Not Use `Void` When You Need a Value

If a downstream step needs `total` as input:

```java
CompletableFuture<Integer> total =
        price.thenCombine(tax, Integer::sum);

CompletableFuture<String> invoice =
        total.thenApply(amount -> "Total=" + amount);
```

These two lines are an excerpt with appropriate `price` and `tax` stages. `thenCombine` returns `Integer` so the downstream pipeline can use it. If you use `thenAcceptBoth` just to `System.out.println` the sum, you have "consumed" the result via a side effect; the stage returns `Void`, so the next step cannot receive that sum.

Decision checklist for choosing the method:

1. **Does the next step need a new value derived from both sources?** `thenCombine`.
2. **Do you need to process/consume both values directly without returning a value?** `thenAcceptBoth`.
3. **Do you only need both to finish, without needing either value?** `runAfterBoth`.
4. **Only one input and a side effect using its value?** `thenAccept`.
5. **Only one input and an action needing no value?** `thenRun`.
6. **Need to coordinate more than two sources?** `allOf` with an appropriate follow-up stage.

Choosing the right method lets the `Void` type reflect the API's intent and avoids hidden dependencies via shared mutable variables.

## 18. There Are No "Two Branches" If You Have Not Started Two Independent Tasks

A common logical mistake:

```java
CompletableFuture<Integer> first =
        CompletableFuture.supplyAsync(() -> loadFirst(), executor);

CompletableFuture<Integer> second =
        first.thenApply(value -> value + 1);

CompletableFuture<Void> done =
        first.runAfterBoth(second, () -> signal());
```

This is an illustrative excerpt. `second` depends on `first`, so the two stages are **not independent**; `runAfterBoth` still obeys completion semantics, but it does not turn the second part into parallel work. If the two sources are genuinely independent:

```java
CompletableFuture<Integer> first =
        CompletableFuture.supplyAsync(() -> loadFirst(), executor);

CompletableFuture<Integer> second =
        CompletableFuture.supplyAsync(() -> loadSecond(), executor);
```

This is also an excerpt. The two sources are submitted independently and **have the opportunity to run in parallel** if the executor has enough workers and the data sources allow it. However, there is no guarantee the JVM will always run them simultaneously on two CPU cores; scheduling, queueing, blocking, and resources determine actual execution.

Do not infer from `runAfterBoth` returning `Void` that the two sources only have side effects. The sources can still return `Integer`, `String`, a `record`, or `Void`; `Runnable` simply **does not receive those results**.

## 19. Handling `null`, Generic Types, and Lambda Captures

`thenAcceptBoth` uses `BiConsumer<? super T, ? super U>`, so generics allow the two sources to have **different types**:

```java
CompletableFuture<String> name =
        CompletableFuture.completedFuture("Java");
CompletableFuture<Integer> version =
        CompletableFuture.completedFuture(17);

CompletableFuture<Void> print =
        name.thenAcceptBoth(version,
                (n, v) -> System.out.println(n + " " + v));
```

This is an excerpt. With `CompletableFuture.completedFuture(null)`, a source can still complete **successfully**, and `thenAcceptBoth` can be invoked with a `null` argument. If the action dereferences `null` without checking, the action itself may throw `NullPointerException`, making the dependent stage exceptional. `null` **does not mean** exceptional completion.

For `runAfterBoth`, the two source types can be completely different, and the callback receives no values. If the callback captures a mutable object from an outer scope, it captures a reference, **not a guaranteed immutable snapshot**. You must consider synchronization and ownership when multiple tasks can read/write the same object.

A syntax distinction: `thenAcceptBoth` takes `(left, right) -> { ... }`; `runAfterBoth` takes `() -> { ... }`. The compiler will reject a `BiConsumer` where a `Runnable` is expected and vice versa.

## 20. Java Memory Model and Happens-Before

For `Future`, actions taken by the asynchronous computation **happen-before** actions following the corresponding `Future.get()` in another thread, per Java's memory consistency contract. `CompletableFuture` performs completion and publication so that dependent actions can observe the results of completed sources according to the Java Memory Model.

For **two branches A and B**, the `thenAcceptBoth` callback only runs on the success path once **both results have been published via completion**, and `runAfterBoth` only runs after the corresponding completion condition is met. This allows the callback to use valid data passed from the sources without polling a plain boolean variable to guess whether both tasks are done.

**Important limitations:**

- It does not make it safe for two sources to increment a plain `int` variable with `++` before the callback runs. The race already happened **inside the two sources**; waiting at the end does not fix the result.
- It does not automatically synchronize mutations **occurring after a source has completed** on a mutable object being read by the callback.
- It does not guarantee a worker is no longer running if a source `CompletableFuture` was canceled/timed out early while the underlying supplier has not exited.
- It does not turn a shared `ArrayList` used by two dependent callbacks into a concurrent collection.
- It does not replace `try/finally`, transactions, or I/O timeouts inside tasks.

Prefer **immutable results**, `record`, `final` fields, snapshots, or `Atomic*` primitives, locks, and concurrent collections when mutable shared state is truly needed. Stage completion marks that data **has been published**, not a guarantee that the entire system outside the JVM is in a consistent state.

## 21. Deadlines, Cancellation, and Executor Lifecycle

Both actions wait for the two sources to succeed, but **have no automatic timeout**. If one source never completes, the dependent stage may never complete; `dependent.join()` will wait indefinitely.

Ways to manage this:

- `dependent.get(timeout, unit)` limits **the caller's wait**, not the two sources themselves.
- `source.orTimeout(timeout, unit)` can complete the source itself with a `TimeoutException`; consequently, the dependent `thenAcceptBoth/runAfterBoth` **does not run the success action**.
- `completeOnTimeout(fallback, ...)` can make a source **complete successfully with a fallback**; the dependent may then run with the fallback — you must decide whether that fits business requirements.
- `CompletableFuture.cancel(true)` **does not guarantee interrupting a running worker**; you need cancellation tokens, I/O timeouts, and separate resource management.
- Use an **overall deadline** from request arrival if the SLA covers queue time, both branches, and the dependent action.
- If the action uses `*Async(..., executor)`, the executor must still be active when the action is submitted; shutting down too early can cause the stage to complete exceptionally due to rejection.

With a custom executor, the owner should call `shutdown()` and `awaitTermination(timeout)` when confirming workers have finished is required. If actions or side effects from the branches are still running, `isDone()` on an unrelated stage is not sufficient proof they have finished. Never shut down `ForkJoinPool.commonPool()` as if it were a per-request resource.

## 22. Side Effects: Logging, Notifications, Caching, and Idempotency

The names "Accept" and "Run" hint that these two methods are often used at side-effect boundaries:

- `thenAcceptBoth`: sending an email/notification using two source payloads, writing an audit entry with both results, updating a view once both price and quantity are available.
- `runAfterBoth`: marking "both steps ready" to advance a phase, releasing a coordination signal, running an action that needs no payload.
- Use `thenCombine` if combining the two sources **must return new data**, such as an order with a calculated total.

Actions outside the JVM are not automatically made transactional by `CompletableFuture`:

1. An action throwing an exception **does not roll back** a partially sent email or file write.
2. Canceling the dependent stage once the action has started **is unlikely to stop an in-progress side effect**.
3. Retrying a pipeline can re-invoke the action and create duplicate side effects without idempotency.
4. Two independent callbacks can perform side effects in an unexpected order.
5. Another consumer might cancel a shared source; you need to define **ownership/cancellation rights**.

When business logic requires exactly-once semantics, use message IDs, deduplication, transactions, or appropriate protocols. Do not assume `CompletableFuture` provides exactly-once guarantees for HTTP requests or databases.

## 23. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Using `thenAcceptBoth` expecting the stage to return a combined value. | The callback returns `void`; the dependent stage is `Void`. | Use `thenCombine` if you need a result `V`. |
| Using `runAfterBoth` and calling `join()` inside the callback to read both sources. | Verbose, error-prone with exceptions and captured state. | Use `thenAcceptBoth` to receive both typed values. |
| Thinking `runAfterBoth` runs if one source fails. | It is a success-dependent action. | Handle errors separately; clean up with `finally`/`whenComplete` under the right contract. |
| Thinking `Void` means the action needs no tracking. | The action can fail or not run yet. | Keep the dependent stage handle and observe success/error. |
| Using `thenAcceptBoth` when the two sources actually depend on each other. | No added parallelism if branch 2 depends on branch 1. | Review the dependency graph and choose a clear API. |
| Assuming non-Async callbacks always run on `main`. | Execution thread depends on completion/scheduler. | Use an Async overload with an `Executor` when control is needed. |
| Assuming `*Async` always spawns a new thread. | Executors typically reuse workers. | Choose the right thread pool and understand its policy. |
| Creating two dependent callbacks and expecting them to run in registration order. | There is no ordering dependency between them. | Chain `thenRun`/`thenCompose` on the previous dependent stage. |
| Performing blocking I/O in a callback on the completing thread. | Can tie up latency-sensitive threads. | Use an appropriate executor and I/O timeouts. |
| Blocking a worker waiting for an action queued on that same executor. | Can cause thread starvation/deadlock. | Use composition; avoid unnecessary `get`/`join` inside workers. |
| Setting `source.orTimeout` and thinking the worker stops automatically. | Timeout changes stage state, not guaranteed to stop computation. | Use cooperative cancellation and separate I/O timeouts. |
| Canceling the dependent stage and expecting upstream and siblings to cancel. | `CompletableFuture` has no automatic structured cancellation. | Design explicit ownership and cancellation protocols. |
| Using `isDone()` as a measure of action success. | Done also includes exceptional and canceled completions. | Use `join/get` or an appropriate error observer. |
| Reading a shared mutable object modified by two tasks and assuming the final callback fixes races. | The data race occurred before the barrier. | Isolate data, use immutable snapshots, or synchronize properly. |
| Using `whenComplete` as a fallback value. | It observes the outcome; it does not turn exceptional into success. | Use `handle` or `exceptionally` with a clear policy. |
| Writing an audit log and discarding the resulting `CompletableFuture<Void>`. | Callback errors may go unobserved. | Track the terminal stage and add metrics/logging. |
| Shutting down the executor before the Async dependent is submitted. | Callback fails with rejection/exceptional completion. | Wait for the pipeline and establish proper lifecycle ownership. |

## 24. Project Application Checklist

1. **Is each source truly independent?** If not, do not assume speedup from "both".
2. **Does the action need the values?** Needs both → `thenAcceptBoth`; needs neither → `runAfterBoth`.
3. **Is a result needed for downstream chaining?** Use `thenCombine` instead of only a side effect.
4. **Do all sources have a completion path?** Never leave a `CompletableFuture` uncompleted forever.
5. **Who executes the callback?** Non-Async / Async / default executor / explicit executor; avoid blocking the completing thread.
6. **Is ordering required between two callbacks?** Declare an explicit dependency instead of relying on registration order.
7. **What if one source fails?** The `both` action will not run; ensure exception handling and resource cleanup paths exist.
8. **What if the action fails?** The dependent stage completes exceptionally; observe via `join/get` or `handle/whenComplete`.
9. **What does cancellation mean?** Canceling Future state does not automatically stop workers; track real tasks when needed.
10. **Is there an overall timeout?** Set a deadline covering both branches and the action, not just a single `get` timeout.
11. **Mutable payload?** Use immutable snapshots or proper synchronization; do not use `Void` to hide races.
12. **External side effects outside the JVM?** Handle idempotency, acknowledgements, or transactions separately.
13. **Are sources shared across multiple callers?** Clarify source cancellation rights and isolate dependent stages.
14. **When is the executor shut down?** After required dependent actions complete and worker/resource lifecycles allow it.
15. **Are failure/cancellation branches tested?** Verify the callback does not run when a source is exceptional, and test when the action itself throws.
16. **Is ordering tested?** Build chains rather than relying on the scheduler.
17. **Are incomplete stages tested?** Use `new CompletableFuture<>()` and scripted `complete()` calls to avoid `sleep`.
18. **Production monitoring:** completion latency, exceptional outcomes, rejected actions, queue depth, and task timeouts.

## 25. Knowledge Self-Check

1. **What does `thenAcceptBoth` wait for?** Both sources to complete normally before invoking the `BiConsumer`.
2. **How does `runAfterBoth` differ?** Its `Runnable` receives neither result from the two sources.
3. **What return type do both methods produce?** A dependent `CompletionStage<Void>`, or `CompletableFuture<Void>` when called on `CompletableFuture`.
4. **Does `Void` mean the dependent stage has no error state?** No; the stage can still have exceptional or canceled completion.
5. **When only source A finishes, has the `both` action run yet?** Not if source B is still incomplete.
6. **What if B completes exceptionally?** The success action does not run, and the dependent stage completes exceptionally.
7. **If the `thenAcceptBoth` callback throws an error, do the two sources become failed?** No; the error belongs to the dependent stage.
8. **Does `thenAcceptBoth` automatically run A and B on two threads?** No; the sources must be created/started separately.
9. **Does `thenAcceptBothAsync` require an `Executor`?** There is a default overload and an overload accepting an explicit `Executor`.
10. **Are `runAfterBoth` and `runAfterEither` the same?** No; `both` requires both stages, while `either` follows one branch per the API contract.
11. **Do two dependent actions waiting on A and B have a fixed order?** No; you must chain them if ordering is required.
12. **When should you use `thenCombine`?** When you want to produce a combined value to pass downstream.
13. **Why is `allOf` not identical to `thenAcceptBoth`?** `allOf` is a barrier for multiple Futures and does not automatically pass two typed results into a `BiConsumer`.
14. **Is `runAfterBoth` a `finally` cleanup for failed sources?** No.
15. **What does a successful `acceptsBoth.join()` return?** `null` for type `Void`, confirming the action stage completed normally.
16. **Does canceling a `CompletableFuture` guarantee interrupting its worker?** No.
17. **Does `get(timeout)` on the dependent stage automatically stop both sources?** No, it only limits the caller's wait.
18. **If A and B have a data race while running, does the `both` barrier fix the race?** No.
19. **Which thread can a non-Async callback run on?** The thread completing a source or a thread participating in completion, with no fixed guarantee.
20. **Should you discard the dependent stage of a mandatory audit action?** No; you need to observe its outcome to ensure errors are not lost.

**Key takeaway:** `thenAcceptBoth(other, BiConsumer)` = **both succeed, take both results to perform an action, return no result**. `runAfterBoth(other, Runnable)` = **both succeed, just run an action without receiving results**. Both return a `CompletionStage<Void>` that can be tracked; if you want a new value use `thenCombine`, if you want ordering **chain dependent stages**, if you want execution on a specific pool use the **Async + Executor** overload, and always handle errors, cancellation, and resource ownership separately.
