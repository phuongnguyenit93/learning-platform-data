# thenCompose() to Chain Asynchronous Tasks in Java CompletableFuture

## 1. Goal: the next task needs the result of the previous task

An asynchronous chain can consist of multiple **data-dependent** steps:

1. Look up a user ID from a request.
2. Once the ID is available, query the profile.
3. Once the profile is available, look up additional information.
4. When the entire chain completes, produce the final result.

Suppose each step returns a `CompletableFuture`. If you write nested callbacks or call `join()` inside a worker to wait for the next step, you easily end up with hard-to-read code and risk occupying the worker unnecessarily. `thenCompose()` is designed to express that **the next step produces a new CompletionStage** without creating a nested future on the caller side.

~~~java
CompletableFuture<String> result =
    lookupUserIdAsync("alice")
        .thenCompose(id -> loadProfileAsync(id))
        .thenCompose(profile -> loadPermissionsAsync(profile));
~~~

This is **illustrative code inside a method**: the three functions `lookupUserIdAsync`, `loadProfileAsync`, and `loadPermissionsAsync` are application-defined with compatible result types. The meaning is that the next step is only invoked when the previous step **completes normally**, and the outermost result reflects the result of the final stage.

### Learning Outcomes

After this lesson, you can:

- Understand the exact generic signature `thenCompose(Function<T, CompletionStage<U>>)`.
- Distinguish `thenApply()` (synchronous value **map**) from `thenCompose()` (asynchronous stage **flatMap**).
- Explain when the mapper function runs, when the resulting stage completes, and why there is no `CompletableFuture<CompletableFuture<T>>`.
- Understand that `thenComposeAsync()` only dispatches **how the compose function executes**, which does not automatically mean all I/O in the inner stage is moved to that executor.
- Design non-blocking `CompletionStage` chains without calling `join/get` inside callbacks.
- Handle exceptional completion from the source stage, mapper, and dependent stage; use `exceptionally`, `handle`, `whenComplete`, and `exceptionallyCompose` in their proper roles.
- Recognize that cancellation/timeout of the resulting stage **does not automatically cascade cancellation or kill background work**.
- Run Java 17+ programs for chaining, flattening, executor routing, and error recovery with deterministic results.
- Avoid dependency cycles, limit pool oversubscription, and control I/O/blocking with dedicated deadlines.

**Scope:** General Java SE concurrency, `java.util.concurrent`; no external libraries or frameworks. Complete programs use JDK 17+.

## 2. The thenCompose() API: signature and semantics

In `CompletionStage<T>`:

~~~java
<U> CompletionStage<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);
~~~

In `CompletableFuture<T>`, the corresponding method returns a `CompletableFuture<U>` according to this class's API.

Explanation of each component:

| Component | Meaning |
|---|---|
| `T` | Result type of the current stage |
| `fn` | Function that receives **value T** of the current stage upon success |
| `CompletionStage<U>` | New stage created/returned by the function |
| `U` | Final data type of the new stage |
| Return value | **A single** stage of type U, completed in accordance with the stage returned by fn |

Mechanism:

~~~text
upstream: CompletionStage<T>
       │
       │ completes normally with T
       ▼
  call fn(T)
       │
       ▼
  inner: CompletionStage<U>
       │
       │ inner completes (normal / exceptional)
       ▼
composed: CompletionStage<U>
       │
       ▼
  caller observes U
~~~

**Only when upstream completes normally** is the function `fn` applied. If upstream completes exceptionally, the mapper is not called; the dependent stage also completes exceptionally according to `CompletionStage` rules. If `fn` returns an incomplete stage, the dependent stage **remains pending** until the inner stage has a result or an error.

One sentence to remember: **`thenCompose()` connects two dependent stages; it does not wait synchronously by holding a thread on `join()`.**

### Analogy with flatMap

With a synchronous value:

~~~java
Optional<String> nickname =
        Optional.of("alice").flatMap(name -> Optional.of(name.toUpperCase()));
~~~

`Optional.flatMap` returns an `Optional` without nesting an `Optional`. Similarly, `thenCompose` returns a `CompletionStage` without nesting a `CompletionStage`. This is a conceptual analogy; it does not mean `Optional` and `CompletableFuture` share the same concurrency mechanism.

## 3. How does thenApply differ from thenCompose?

### thenApply: Function returns a **regular value**

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("123")
                .thenApply(Integer::parseInt);
~~~

Here `Integer.parseInt` returns `int/Integer`, so the result is `CompletableFuture<Integer>`.

If `thenApply` receives a function returning **a CompletableFuture**:

~~~java
CompletableFuture<CompletableFuture<Integer>> nested =
        CompletableFuture.completedFuture("12")
                .thenApply(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text)));
~~~

The result is nested **two levels deep**. `nested.join()` returns `CompletableFuture<Integer>`, and to get the actual number the caller must call `nested.join().join()` — adding an unnecessary layer of management.

### thenCompose: Function returns **CompletionStage**

~~~java
CompletableFuture<Integer> flat =
        CompletableFuture.completedFuture("12")
                .thenCompose(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text)));
~~~

`flat` is a `CompletableFuture<Integer>`. There is no nested future in the return type.

| Question | `thenApply` | `thenCompose` |
|---|---|---|
| What does the mapper return? | Value `U` | `CompletionStage<U>` |
| Result type | `CompletableFuture<U>` | `CompletableFuture<U>` |
| If mapper returns a CF<U> | `CF<CF<U>>` | `CF<U>` |
| Primary use case | Synchronous transformation from T to U | Next step is **itself asynchronous**, depending on T |
| Does it wait by blocking a worker? | Does not wait on its own | Does not wait on its own |
| What happens when upstream fails? | Does not call mapper | Does not call mapper |

**Do not "replace every thenApply with thenCompose".** If the function returns a value immediately like `String::toUpperCase`, using `thenApply` is right. If the function returns `CompletionStage<U>`, `thenCompose` is right.

## 4. Runnable Example 1: comparing nested and flattened

Save **ThenComposeVsApplyDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class ThenComposeVsApplyDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("21");

        CompletableFuture<CompletableFuture<Integer>> nested =
                source.thenApply(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text) * 2));

        CompletableFuture<Integer> flat =
                source.thenCompose(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text) * 2));

        System.out.println("nested=" + nested.join().join());
        System.out.println("flat=" + flat.join());
    }
}
~~~

Compile and run:

~~~bash
javac ThenComposeVsApplyDemo.java
java ThenComposeVsApplyDemo
~~~

Stdout:

~~~text
nested=42
flat=42
~~~

Both computations produce 42; **the difference lies in the result type and the chaining model**. `nested.join().join()` has to unwrap two layers. `flat.join()` only unwraps one layer.

### Note on operators and method references

`thenCompose` does not accept a parameterless `Supplier<CompletionStage<U>>` when upstream has result T; it accepts `Function<T, CompletionStage<U>>`. If the next step does not need the value T, still use a lambda taking the parameter and intentionally ignore it:

~~~java
CompletableFuture<String> next =
    CompletableFuture.completedFuture("ignored")
        .thenCompose(unused ->
                CompletableFuture.completedFuture("ready"));
~~~

If you only want to **run a task after a stage** without needing the result, `thenRun` or `thenRunAsync` may be more appropriate. If you want to run a `Runnable` and return `CompletableFuture<Void>`, design the return type accordingly.

## 5. Runnable Example 2: chaining two dependent asynchronous tasks

This is a complete Java 17+ program using an **application-owned executor**. Step 1 creates a user ID; step 2 is only called once the ID is available; step 3 transforms the returned string.

Save **ThenComposePipelineDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenComposePipelineDemo {
    static CompletableFuture<String> findId(
            String name, ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> "id-" + name, executor);
    }

    static CompletableFuture<String> findRole(
            String id, ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> id + ":reader", executor);
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<String> answer =
                    findId("alice", executor)
                            .thenCompose(id -> findRole(id, executor))
                            .thenApply(role -> "result=" + role);

            System.out.println(answer.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Commands:

~~~bash
javac ThenComposePipelineDemo.java
java ThenComposePipelineDemo
~~~

Stdout:

~~~text
result=id-alice:reader
~~~

**Explanation:**

1. `findId` returns `CompletableFuture<String>`. `supplyAsync` submits the supplier to the executor.
2. When `findId` succeeds with `"id-alice"`, the function passed to `thenCompose` finally has a valid input to call `findRole`.
3. `findRole` returns **another CompletableFuture**; the resulting stage of `thenCompose` takes on the completion of this stage.
4. `thenApply` transforms the role into the final string, because this step returns a synchronous value.
5. `answer.join()` appears **only at the main boundary** so the console program waits for the output and prints it; there is no `join` call inside a worker-stage callback.
6. The executor is shut down in `finally` to avoid keeping platform threads alive after completion.

The program does not rely on thread names, scheduling order, or sleep durations; therefore stdout is deterministic. Whether steps 1 and 2 run on the same or different workers, **step 2 needs the ID so it cannot use the result before step 1 completes**.

### Remark on the two tasks

Because step 2 needs the ID from step 1, the steps **have no inherent parallel speedup between themselves**. `thenCompose` describes an **asynchronous dependency**, not a way to run two dependent tasks concurrently. To run two **independent** tasks, see `thenCombine` or `allOf`, then combine the results.

## 6. thenCompose does not call the function before upstream succeeds

Use a manually controlled `CompletableFuture` to observe exactly when the mapper runs and when the composed stage completes, without using `Thread.sleep()`.

Save **ThenComposeOrderingDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenComposeOrderingDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        AtomicInteger mapperCalls = new AtomicInteger();

        CompletableFuture<String> result =
                first.thenCompose(id -> {
                    mapperCalls.incrementAndGet();
                    return second.thenApply(value -> id + ":" + value);
                });

        System.out.println("before=" + mapperCalls.get());
        first.complete("user-7");
        System.out.println("afterFirst=" + mapperCalls.get());
        System.out.println("doneAfterFirst=" + result.isDone());

        second.complete("ready");
        System.out.println("afterSecond=" + result.join());
    }
}
~~~

Compile/run:

~~~bash
javac ThenComposeOrderingDemo.java
java ThenComposeOrderingDemo
~~~

Stdout:

~~~text
before=0
afterFirst=1
doneAfterFirst=false
afterSecond=user-7:ready
~~~

**Why is there no race in the output?**

- `first` and `second` are incomplete `CompletableFuture`s. Before `first.complete`, the mapper has no input value to run with.
- `thenCompose` (non-Async version) attaches a dependent action; when `main` calls `first.complete("user-7")`, the callback can be executed by `main` during completion.
- `first.complete` returns after the dependent action has been triggered for this chain in this example model; `mapperCalls` is 1 when printing `afterFirst`.
- The mapper returns `second.thenApply(...)`, but `second` is still pending, so the composed result is not done yet.
- `second.complete("ready")` causes the dependent stage to compute the string; `result.join()` returns `"user-7:ready"`.

**Consequence:** `thenCompose` is not `join` in disguise. It only wires the dependency graph and returns a new stage; completion can happen in the future.

## 7. Synchronous and asynchronous variants of compose

The three important overloads of `CompletableFuture`:

~~~java
<U> CompletableFuture<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);

<U> CompletableFuture<U> thenComposeAsync(
        Function<? super T, ? extends CompletionStage<U>> fn);

<U> CompletableFuture<U> thenComposeAsync(
        Function<? super T, ? extends CompletionStage<U>> fn,
        Executor executor);
~~~

Differences:

- `thenCompose(fn)`: the dependent function may run on the thread that **completed the previous stage** or a thread involved in completion; it **does not guarantee** spawning a new worker or running on a different executor.
- `thenComposeAsync(fn)`: the function is dispatched using the stage's **default asynchronous execution facility**; for the default `CompletableFuture` this is typically `ForkJoinPool.commonPool()`, with an API-defined fallback when parallelism does not meet requirements.
- `thenComposeAsync(fn, executor)`: the function is dispatched using the **specified Executor**; easier to control thread naming, quotas, ownership, and monitoring.
- All three still **compose the result of the stage returned by fn**; they do not automatically turn a blocking external operation into a non-blocking operation.

### An important misconception

~~~java
source.thenComposeAsync(value -> slowBlockingCall(value), executor);
~~~

If `slowBlockingCall` **returns a CompletionStage** after a small amount of synchronous logic, the mapper part is invoked by the executor. But if `slowBlockingCall` **blocks for 30 seconds before returning the stage**, the executor thread is still blocked for 30 seconds. If the method directly returns `String` instead of `CompletionStage`, the code does not match the `thenCompose` signature.

For true asynchronous I/O, the choice depends on the API: a non-blocking client returning a stage, or using an appropriate executor for blocking work via `supplyAsync`, with timeouts and concurrency limits.

## 8. Runnable Example 4: thenComposeAsync with a specified executor

Save **ThenComposeExecutorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenComposeExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "compose-worker"));

        try {
            CompletableFuture<String> output =
                    CompletableFuture.completedFuture("payload")
                            .thenComposeAsync(value ->
                                    CompletableFuture.completedFuture(
                                            Thread.currentThread().getName()
                                                    + ":" + value),
                                    executor);

            System.out.println(output.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ThenComposeExecutorDemo.java
java ThenComposeExecutorDemo
~~~

Stdout:

~~~text
compose-worker:payload
~~~

**Reason:** the executor has only one thread named `compose-worker`, and the `thenComposeAsync(fn, executor)` overload runs the mapper on that executor. The mapper uses `Thread.currentThread().getName()` **inside the callback**, not relying on the name of the thread running `main` or the source stage. The inner stage is already completed immediately with `completedFuture`; there is no other I/O task to dispatch.

Do not infer from this example that every subsequent step in the chain runs on `compose-worker` by default. A `supplyAsync` inside the mapper using **its own executor** will execute the supplier on that executor; a subsequent non-Async `thenApply` has its own completion-thread policy.

## 9. Choosing an executor: each stage's responsibility

Model example:

~~~java
CompletableFuture<String> pipeline =
    CompletableFuture.supplyAsync(() -> readInput(), ioExecutor)
        .thenCompose(input -> queryAsync(input))
        .thenApply(result -> normalize(result))
        .thenComposeAsync(normalized -> writeAsync(normalized), writeExecutor);
~~~

This is an **integration illustration**, where functions and executors are application-defined. Before choosing an overload, ask:

1. Is `readInput()` blocking? If so, does `ioExecutor` have a reasonable limit on worker count?
2. Does `queryAsync()` already return an asynchronous stage that manages its own I/O? Is it necessary to dispatch the mapper separately?
3. Is `normalize()` a short CPU transformation or heavy work? If heavy, should `thenApplyAsync(..., cpuExecutor)` be used?
4. What are the side effects/idempotency, timeout, and cancellation policies of `writeAsync()`?
5. Who owns `ioExecutor` and `writeExecutor`, and when are they shut down?
6. Do callbacks hold locks or wait on a `Future` from the same single-threaded executor?

**Not every stage needs Async.** Using Async everywhere can create unnecessary queue/context-switching overhead. Conversely, a long CPU-bound callback in a non-Async stage can occupy the thread completing upstream and introduce latency to other completions.

### The common pool is not the right default for all I/O

If you rely on `supplyAsync` without passing an executor for many blocking calls, the load can contend with other work on `ForkJoinPool.commonPool()`. Consider a dedicated executor, limiting concurrent requests, backpressure, and appropriate timeouts. With Java 21+, virtual threads can be helpful for blocking I/O, but they **do not automatically** limit downstream connections/rate; avoid treating them as a reason to drop admission limits.

## 10. Source stage failure: mapper is not called

If the source future fails, the `thenCompose` lambda does not run:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));

CompletableFuture<String> composed =
        failed.thenCompose(value ->
                CompletableFuture.completedFuture("never"));
~~~

`composed` completes exceptionally according to `CompletionStage` rules. Importantly, it **does not dispatch the dependent step** as if the source had succeeded. These are the fail-fast semantics usually desired when the next step strictly requires data from the previous step.

Common failure sources:

| Failure point | Consequence |
|---|---|
| Upstream completed exceptionally | Compose function is not called, dependent is exceptional |
| Mapper itself throws an exception before returning CompletionStage | Dependent is exceptional |
| Inner CompletionStage completes exceptionally | Composed stage is exceptional matching the inner stage |
| Mapper returns null instead of CompletionStage | No valid stage to compose, dependent is exceptional (typically NullPointerException) |

**Do not swallow exceptions by returning null** when a method must return `CompletionStage`. If business logic needs "no data", return a normally completed stage with an appropriate domain value such as `Optional.empty()`, or `completedFuture(null)` if `null` has a clear meaning; that is different from **returning null for the CompletionStage itself**.

## 11. Recovery: exceptionally, handle, whenComplete, and exceptionallyCompose

These APIs serve different roles.

### exceptionally: recover with a value T

~~~java
CompletableFuture<String> result = pipeline
        .exceptionally(error -> "fallback-value");
~~~

Runs only when the previous stage fails; returns a regular value to restore normal completion of the dependent stage. Do not use `exceptionally` to **return a CompletableFuture<String>** when the expected type is `String`.

### exceptionallyCompose: recover with an asynchronous stage

Java 12+ has `exceptionallyCompose`:

~~~java
CompletableFuture<String> result =
        primaryAsync()
                .exceptionallyCompose(error ->
                        fallbackAsync(error));
~~~

This snippet requires the application to provide `primaryAsync` and `fallbackAsync` with matching types. This is an **asynchronous branch used only when primary fails**, analogous to `thenCompose` but applied on the exceptional-completion path. It does not automatically cancel primary I/O if primary already has side effects.

### handle: observe both success and failure, transform into a value

~~~java
CompletableFuture<String> summarized = pipeline.handle(
        (value, error) -> error == null
                ? "ok:" + value
                : "failed");
~~~

`handle` runs on both branches and can map the outcome to a new result. Thus it is useful for converting success/failure into a unified return type.

### whenComplete: observe side effects like metrics/logging

~~~java
CompletableFuture<String> logged = pipeline.whenComplete(
        (value, error) -> recordOutcome(value, error));
~~~

This is an integration snippet with an application-defined `recordOutcome`. `whenComplete` is **not** meant to replace the result like `handle`; it preserves the upstream value/exception unless the callback throws an exception per the Javadoc rules. Use it for lightweight logging/metrics/cleanup, and avoid making the callback block for long.

### Choosing where to place recovery

~~~text
A.thenCompose(B).exceptionally(fallback)
  → catches failures of both A and B

A.exceptionally(fallbackA).thenCompose(B)
  → recovers A first, then B is called with the fallback value

A.thenCompose(B).exceptionallyCompose(fallbackAsync)
  → failure of A or B triggers the asynchronous fallback

A.thenCompose(B).handle(outcome)
  → transforms both success/failure into a new result type
~~~

Operator placement **has semantic meaning**, not just code style.

## 12. Runnable Example 5: exceptional completion and fallback

Save **ThenComposeErrorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenComposeErrorDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        CompletableFuture<String> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("primary unavailable"));

        CompletableFuture<String> pipeline = source.thenCompose(value -> {
            calls.incrementAndGet();
            return CompletableFuture.completedFuture("unused");
        });

        String recovered = pipeline
                .exceptionally(error -> "fallback")
                .join();

        CompletableFuture<String> secondaryFailure =
                CompletableFuture.completedFuture("user")
                        .thenCompose(id ->
                                CompletableFuture.<String>failedFuture(
                                        new IllegalArgumentException("bad id")));

        String outcome = secondaryFailure
                .handle((value, error) ->
                        error == null ? "ok" : "failed")
                .join();

        System.out.println("mapperCalls=" + calls.get());
        System.out.println("recovered=" + recovered);
        System.out.println("innerOutcome=" + outcome);
    }
}
~~~

Commands:

~~~bash
javac ThenComposeErrorDemo.java
java ThenComposeErrorDemo
~~~

Stdout:

~~~text
mapperCalls=0
recovered=fallback
innerOutcome=failed
~~~

**Explanation:**
- Source had already failed before compose, so the mapper did not run; `calls` remains 0.
- `exceptionally` creates a dependent stage that completes normally with `"fallback"`.
- In the second call, source `"user"` completes normally, and the mapper returns **a failed future**. The composed stage receives that error; `handle` converts it into the string `"failed"`.
- The program does not need to predict exception messages or thread scheduling to print the exact output.

### Finding the root cause of join

`join()` typically throws `CompletionException` with a cause originating from the upstream/mapper/inner stage; for direct cancellation it may throw `CancellationException` per the contract. `get()` throws `ExecutionException` (checked) and can throw `InterruptedException`. Do not use `join` as a way to "turn an error into a value"; if you want recovery, attach `exceptionally`/`handle` to the stage chain.

## 13. Why not call join/get right inside thenCompose?

A common mistake:

~~~java
CompletableFuture<User> brokenShape =
        loadIdAsync()
                .thenCompose(id -> {
                    User user = loadUserAsync(id).join();
                    return CompletableFuture.completedFuture(user);
                });
~~~

This is **incorrect illustrative code** with application-defined methods and type `User`. If `loadUserAsync(id)` has not completed yet, `join()` **blocks the thread executing the callback**. This defeats the purpose of composition and can cause starvation if the inner work needs the very worker currently blocked.

The right way:

~~~java
CompletableFuture<User> good =
        loadIdAsync()
                .thenCompose(id -> loadUserAsync(id));
~~~

If you actually need to transform `User` after the inner stage finishes:

~~~java
CompletableFuture<String> display =
        loadIdAsync()
                .thenCompose(id -> loadUserAsync(id))
                .thenApply(user -> user.displayName());
~~~

Both are integration snippets. There is no `join()` in the mapper; `join()` should only be used at a boundary where a synchronous result is **genuinely needed**, such as `main`/CLI/tests or an imperative API with clear semantics.

### Thread-starvation deadlock

Scenario:
1. An executor has **one worker**.
2. A callback runs on that worker.
3. The callback submits another task to the **same executor**.
4. The callback calls `join()` waiting for the new task.
5. The new task is queued, with no free worker.
6. The sole worker remains held by the callback until `join` returns.

This can wait indefinitely. Replace it with non-blocking `thenCompose` so the worker returns execution control to the executor. However, you must also avoid a real **dependency cycle**: stage A depends on B, while B depends on A. Composition cannot automatically resolve a cyclic graph.

## 14. Return type CompletionStage or CompletableFuture?

The interface signature accepts `CompletionStage<U>`. Therefore, the mapper does not have to return a concrete `CompletableFuture<U>`: it can return another `CompletionStage` implementation if compatible.

Example:

~~~java
CompletionStage<Integer> stage =
        CompletableFuture.completedFuture("12")
                .thenCompose(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text)));
~~~

In Java code, `CompletionStage` conveys a **graph of dependent computations**; `CompletableFuture` adds `complete`, `cancel`, `join`, `get`, and concrete methods. If an API design only wants to expose chaining capabilities, it can return `CompletionStage<T>` instead of giving the caller power to directly complete the internal future.

**Note:** the concrete type difference affects the ability to call `join` directly. The `CompletionStage` interface does not have `join`; to wait using the `CompletableFuture` API, one typically calls `toCompletableFuture()` (with a supporting implementation).

### Generic inference

`thenCompose` has type parameter `U`. One function returning `CompletionStage<String>` and another returning `CompletionStage<Integer>` will need an explicit mapping/union type if used in the same branch. If a lambda has multiple branches with mismatched return types, the compiler may fail to infer the desired `U`.

Choose a unified domain return type and avoid raw `CompletionStage`/raw `CompletableFuture` to preserve static type safety.

## 15. Cancellation and timeout: compose does not automatically tear down the work chain

`CompletableFuture.cancel(true)` takes effect on **completion state**, not as an interrupt command to a running thread as beginners often expect. The `CompletableFuture` Javadoc states that `mayInterruptIfRunning` **has no effect** in this implementation; interrupts are not used to control processing that way.

Scenarios:

- Cancelling the **composed stage** has no contract to automatically cancel all upstream or inner stages.
- Cancelling the source `CompletableFuture` can cause the dependent stage to complete exceptionally, but does not necessarily abort actual I/O work running at the source.
- An already-created inner stage may continue running after the composed stage is cancelled.
- `orTimeout` and `completeOnTimeout` complete **the specific CompletableFuture they are called on** if not done within the deadline (one with an exception, one with a value); they do not automatically stop all external tasks/connections.
- `get(timeout, unit)` limits **how long the caller waits** and **does not automatically cancel** the future.
- `join()` takes no timeout and can wait indefinitely.

### Example of timeout on a composed stage

~~~java
CompletableFuture<Result> composed =
        loadIdAsync()
                .thenCompose(id -> queryAsync(id));

composed.orTimeout(500, TimeUnit.MILLISECONDS);
~~~

This is an integration snippet using `Result` and application methods; `orTimeout` has been available since Java 9. If the deadline expires before `composed` completes, it completes exceptionally with `TimeoutException`. **Do not assume `queryAsync` has stopped**: that depends on the timeout/cancellation of the I/O API and the backend system itself.

If business logic requires an **overall** timeout across multiple stages, maintain a shared deadline instead of giving each step a full new timeout:
- Compute the deadline using `System.nanoTime()` and a budget.
- Before each step, compute the remaining time.
- Do not let a later stage start a request with an already expired deadline.
- Configure timeouts on the client/network operation according to its contract.
- If cleanup is needed, design the owner to perform cancellation at each source, close resources, or stop the pipeline.

### Cancelling after side effects have occurred

If step 2 has already written external data and then step 3 times out, cancellation does not undo step 2. Write steps may need idempotency keys, a transaction protocol, or compensation. A `CompletableFuture` graph is not a transaction manager.

## 16. Returning a null stage: a subtle anti-pattern

Writers sometimes return `null` instead of a `CompletionStage`:

~~~java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("id")
                .thenCompose(id -> null); // Wrong: no CompletionStage to compose
~~~

This is an error-illustration snippet. When the function returns `null`, the dependent stage completes exceptionally due to the lack of a valid stage; a `NullPointerException` may appear in the cause. If `null` is a **valid data value**, return an actual stage:

~~~java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("id")
                .thenCompose(id ->
                        CompletableFuture.completedFuture(null));
~~~

Distinguish:
- `return null;`: **no stage** to compose.
- `return CompletableFuture.completedFuture(null);`: a stage that completes normally with **value null**.

If `null` means not found, consider `CompletableFuture<Optional<T>>` or an explicit domain result type to avoid null-laden code.

## 17. thenCompose does not guarantee retry or fallback

A chain:

~~~java
loadIdAsync().thenCompose(id -> loadUserAsync(id))
~~~

does not automatically:
- Retry when `loadUserAsync` fails.
- Switch to a backup source.
- Wait for another source to succeed.
- Run multiple independent sources simultaneously.
- Limit concurrent requests.
- Cancel upstream work if downstream times out.

Those capabilities must be designed explicitly:

| Need | Appropriate tool |
|---|---|
| Run the next step depending on the previous step's result | `thenCompose` |
| Transform a value synchronously | `thenApply` |
| Combine **two independent tasks** with results | `thenCombine` |
| Wait for multiple independent futures to all complete | `CompletableFuture.allOf` |
| Wait for one future to complete early (including failure) | `CompletableFuture.anyOf` |
| Handle fallback with a value | `exceptionally` |
| Fallback with a new stage | `exceptionallyCompose` |
| Observe outcome | `whenComplete` |
| Choose recovery for both success/failure | `handle` |
| Bound completion time of a CF | `orTimeout` or `completeOnTimeout` |
| Wait with timeout on caller | `get(timeout, unit)` |

If you want the "first successful response" among multiple futures, `anyOf` is not equivalent because the first future to finish could fail and `anyOf` completes exceptionally; you need a coordinator with an explicit success policy or another appropriate API.

## 18. Relation to thenCombine and allOf: sequential by dependency, not waiting on all branches

Example where A and B are independent:

~~~java
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 10, executor);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 20, executor);

CompletableFuture<Integer> sum =
        a.thenCombine(b, Integer::sum);
~~~

This is an integration snippet with `executor` defined. Both `a` and `b` can be scheduled independently; `thenCombine` waits for both and then adds them. **Do not use `thenCompose` to force `b` to start after `a` if they are truly independent**, as that unnecessarily limits parallelism.

When B needs A:

~~~java
CompletableFuture<Integer> chained =
        a.thenCompose(value ->
                CompletableFuture.supplyAsync(
                        () -> expensiveStep(value), executor));
~~~

If B depends on A, having B start only after A is **correct business logic**. Choose the API based on the dependency graph, not the number of stages.

## 19. No guarantee on the execution thread of non-Async callbacks

A completion timing race:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> result =
        source.thenCompose(value -> makeStage(value));
~~~

If `source` is not yet complete, the callback is registered and may be run when `source` completes. If `source` is already complete, the callback may run immediately on the thread attaching the dependent stage. If `source` completes from another thread, the completing thread may run that callback. The `CompletableFuture` Javadoc does not guarantee that a non-Async callback will always run on a fixed thread.

Consequences:
- Do not depend on `Thread.currentThread().getName()` unless an executor policy is specified and tested appropriately.
- Non-Async callbacks should be **lightweight** and not block for long.
- Do not hold a `synchronized` lock and complete a `CompletableFuture` whose callbacks might block or contend on the same resource; avoid lock-ordering cycles.
- Avoid updating shared mutable state in the mapper without proper memory visibility/synchronization.
- If you need to route the callback onto a specific executor, use the `thenComposeAsync(fn, executor)` overload.

### Async does not guarantee progress if the pool is starved

Even when using `thenComposeAsync`, if the executor has been shut down, the async task may be rejected and the dependent stage may complete exceptionally. If the executor has only one worker and the mapper tries to `join` a new task submitted to the same pool, starvation can still occur. Async operators help **dispatch the function**; they cannot fix a broken dependency graph.

## 20. Designing a resource-bounded pipeline

A real system needs to address questions beyond syntax:

**Input:** how many requests arrive concurrently? Are there limits, queues/backpressure?

**Data sources:** does each stage return a true `CompletionStage` or does it block a thread before returning? If it blocks, how many threads does the executor have? Does downstream have connection limits/rate quotas?

**Results:** what do `null` or empty values mean? Is validation needed before the next step?

**Exceptions:** should a single stage failure fail the pipeline, or is bounded fallback/retry needed? If retrying, are there an overall deadline and idempotency?

**Lifecycle:** who owns the executor, when is it shut down, and are there still incomplete inner stages?

**Observability:** measure queue time, per-stage duration, error/timeout rates, count of cancelled tasks still performing I/O, and tail latency.

**Data safety:** data passed between stages should be immutable or have clear ownership. `CompletableFuture` provides appropriate memory consistency guarantees when passing completions/results if used properly, but it **does not automatically protect** concurrent mutations to a shared external object.

## 21. An API design example better than nested callbacks

### Deeply nested callbacks, hard to manage

~~~java
startAsync().thenAccept(id -> {
    loadAsync(id).thenAccept(record -> {
        enrichAsync(record).thenAccept(enriched -> {
            saveAsync(enriched).thenAccept(saved -> {
                logResult(saved);
            });
        });
    });
});
~~~

This is an illustrative snippet with application methods. Problems:
- The outer stage can complete **before** the inner callbacks.
- Exceptions in inner chains may not be observed/propagated to the expected caller object.
- Users struggle to add a pipeline-level timeout, fail-fast, or logging.
- Cancellation and lifecycle responsibilities are scattered.

### Composing a clear graph

~~~java
CompletableFuture<Result> pipeline =
        startAsync()
            .thenCompose(id -> loadAsync(id))
            .thenCompose(record -> enrichAsync(record))
            .thenCompose(enriched -> saveAsync(enriched))
            .whenComplete((result, error) ->
                    logOutcome(result, error));
~~~

This is an integration snippet, with `Result` and methods defined by the application. When methods return compatible `CompletableFuture`/`CompletionStage` instances, you get **a single result graph** for the caller to monitor, time out, log, and handle errors. Each stage is connected with `thenCompose` instead of a `thenAccept` callback that does not return/await the inner stage.

**Note:** `whenComplete` returns another dependent stage; your logging can also fail. To ensure the original exception is not lost, logging should avoid throwing unexpected exceptions.

## 22. Common mistakes found during code review

**Mistake 1:** Using `thenApply` for a function returning `CompletableFuture` and getting an unwanted `CF<CF<T>>`. Use `thenCompose` when flattening is needed.

**Mistake 2:** Using `thenCompose` for a function that only returns `String`/`Integer`. The mapper must return `CompletionStage<U>`, not `U`.

**Mistake 3:** Calling `join()` inside the mapper to turn a future into a regular value. It blocks the callback thread; use non-blocking composition.

**Mistake 4:** Assuming `thenCompose` automatically spawns a new thread. Non-Async has no thread-hop guarantee.

**Mistake 5:** Assuming `thenComposeAsync` automatically makes all inner operations asynchronous. It dispatches the callback via the executor; the method returning the stage can still block before returning.

**Mistake 6:** Ignoring upstream failures; the mapper does not run when upstream is exceptional, so recovery must be placed at the right spot.

**Mistake 7:** Mapper returning a `null` `CompletionStage`. That is an error, not a "future completed with null".

**Mistake 8:** Using `exceptionally` to return a `CompletableFuture` when the dependent type is `T`. Use `exceptionallyCompose` for a fallback stage.

**Mistake 9:** Placing a fallback too early and accidentally allowing subsequent steps to run with inappropriate data. Choose the recovery point according to business logic.

**Mistake 10:** Thinking `CompletableFuture.cancel(true)` interrupts a running worker. The default implementation does not use `mayInterruptIfRunning` as a kill command.

**Mistake 11:** Thinking `orTimeout` aborts network I/O and rolls back writes. It controls the completion of the `CF`; I/O needs its own timeout/cancellation.

**Mistake 12:** Assuming `get(timeout)` automatically cancels the task. It only bounds the caller's wait.

**Mistake 13:** Putting two independent tasks into a `thenCompose` chain, losing necessary parallelism. Use `thenCombine`/`allOf` when appropriate.

**Mistake 14:** Assuming upstream success makes the entire pipeline done even while the inner stage is still pending. The composed stage waits for inner completion.

**Mistake 15:** Creating a dependency cycle, e.g., stage A waits on stage B and B waits on A. The `CompletableFuture` graph can still fail to make progress.

**Mistake 16:** Failing to shut down an owned executor, keeping platform threads alive unnecessarily. Conversely, shutting down a **shared** executor after one request is also wrong ownership.

**Mistake 17:** Not handling `CompletionException` at the boundary, obscuring the real error. Inspect the cause and log according to policy.

**Mistake 18:** Forgetting concurrent request limits; each request chaining multiple I/O calls can overload downstream. Use semaphores, bounded queues, connection limits/rate limits.

**Mistake 19:** Sharing mutable data across multiple callbacks without thread safety. A thread-safe stage result does not make every referenced object immutable.

**Mistake 20:** Using a callback chain as a substitute for a transaction manager. When a later step fails, side effects from earlier steps are not automatically rolled back.

## 23. Application Checklist

- [ ] Does the next step **depend on value T** from the previous step?
- [ ] Does the mapper return `CompletionStage<U>`, rather than `U` or `null`?
- [ ] Are you using `thenApply` for synchronous mapping and `thenCompose` for an async stage?
- [ ] Have you avoided `join/get` inside callbacks on workers?
- [ ] Are you aware that both source failure and inner failure make the composed stage exceptional?
- [ ] Do you need a fallback with a value or with a new stage?
- [ ] Does the async overload use the right executor for the CPU/I/O workload?
- [ ] Are you avoiding assuming non-Async callbacks run on a fixed thread?
- [ ] Have blocking work, queue capacity, and downstream concurrency been bounded?
- [ ] Are there an overall deadline, per-I/O-stage timeouts, and dedicated cleanup?
- [ ] Are you avoiding assuming cancellation automatically propagates to all futures/inner tasks?
- [ ] Is per-stage outcome logging/tracing in place with an appropriate correlation ID?
- [ ] Do data objects have clear ownership to avoid races?
- [ ] Are errors from both the mapper and the inner stage handled?
- [ ] If parallel independent stages are needed, are `thenCombine`/`allOf` used?
- [ ] Does the executor have a clear owner and shutdown/`awaitTermination`?
- [ ] Do tests coordinate completion with `CompletableFuture.complete` or latches, rather than sleeping to guess the scheduler?
- [ ] After side effects, have idempotency, retry budgets, and transaction consistency been addressed?

## 24. Self-Check Exercises

**Question 1.** What is the result type of `thenApply(id -> loadAsync(id))` when `loadAsync` returns `CompletableFuture<User>`?

**Answer:** `CompletableFuture<CompletableFuture<User>>` (assuming the source is `CompletableFuture<String>`).

**Question 2.** If changed to `thenCompose(id -> loadAsync(id))`, what is the result type?

**Answer:** `CompletableFuture<User>`.

**Question 3.** Stage A completes exceptionally; is the function passed to `A.thenCompose(fn)` called?

**Answer:** No. The dependent stage completes exceptionally; appropriate recovery is needed if you want to continue.

**Question 4.** A succeeds, and `fn` returns an incomplete `CompletableFuture`. Is the composed stage done yet?

**Answer:** No; it tracks the completion of the inner stage.

**Question 5.** What does `thenComposeAsync(fn, executor)` guarantee?

**Answer:** The compose function is executed via the specified executor; it does not promise that all inner work also runs on that executor.

**Question 6.** An inner stage completes exceptionally. What happens to the composed stage?

**Answer:** It completes exceptionally; `join`/`get` at the boundary will surface the error according to its respective contract.

**Question 7.** When a mapper wants to return a valid `null` value, should it `return null` or `return completedFuture(null)`?

**Answer:** `completedFuture(null)`. Returning `null` instead of a stage violates the contract.

**Question 8.** Why can `join()` inside a mapper cause a deadlock on a single-worker executor?

**Answer:** The mapper holds the worker waiting for a new task submitted to that same executor, while no worker is free to run the new task.

**Question 9.** Steps A and B are independent, and you need `A + B`. Is using `thenCompose` to run B after A optimal?

**Answer:** No. You should start A and B independently and then use `thenCombine` or `allOf` to combine them when both finish.

**Question 10.** Does `CompletableFuture.cancel(true)` guarantee interrupting work behind a composed stage?

**Answer:** No. The Javadoc states that the `mayInterruptIfRunning` parameter has no effect in the default `CompletableFuture`, and cancellation does not automatically propagate across the graph.

**Question 11.** Does `orTimeout(100, MILLISECONDS)` guarantee that the remote request has stopped at 100ms?

**Answer:** No. It completes the `CompletableFuture` exceptionally upon timeout; it does not automatically manage remote resources.

**Question 12.** What should you use if you only want an asynchronous fallback when the pipeline fails?

**Answer:** `exceptionallyCompose(error -> fallbackAsync(error))` with Java 12+.

## 25. Official Documentation

- **CompletableFuture — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **CompletionStage — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **Executor — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- **ExecutorService — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **ForkJoinPool — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **TimeUnit — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html
- **Future — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html

**Conclusion:** `thenCompose()` is the **flatMap of CompletionStages**, enabling you to chain **result-dependent** asynchronous steps without creating nested futures or blocking workers with `join()`. The outer stage only completes when the stage returned by the mapper completes; upstream/mapper/inner-stage errors propagate via exceptional-completion rules. Use `thenComposeAsync` when an executor policy is genuinely needed, `thenApply` for synchronous transformations, `thenCombine` for independent branches, and manage timeouts/cancellation/side effects of background work separately.
