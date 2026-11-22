# Callbacks Without the Async Suffix May Run on the Completing Thread or the Calling Thread — Java CompletableFuture

> **Scope:** Java SE 17, the **CompletableFuture** part of general Java concurrency. This article explains an easily overlooked rule: dependent callbacks such as `thenApply`, `thenAccept`, `thenRun`, `whenComplete`, `handle`, and `thenCompose` **without the Async suffix** do not own a dedicated executor, and may be executed on **the thread completing the source stage** or **the thread calling/registering the completion when the source is already completed**. Spring-related concurrency belongs to a separate chapter; no Spring APIs are used in this article.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain **dependent stage** and **completion action** in `CompletableFuture`.
2. Distinguish **asynchronous computation** from **asynchronous callback dispatch**: a source created with `supplyAsync` does not turn every `thenApply` callback into `thenApplyAsync`.
3. Explain why a non-`Async` callback may run on the thread calling `complete` when registered beforehand, or on the thread calling `thenApply` when the source is already completed.
4. Understand the exact boundaries of the JavaDoc: it is a **policy allowing multiple threads to participate in execution**, not a contract that it "always runs on the completer" or "always runs on the caller."
5. Compare `thenApply`/`thenApplyAsync`, `thenAccept`/`thenAcceptAsync`, `thenCompose`/`thenComposeAsync`, and `whenComplete`/`whenCompleteAsync`.
6. Understand the meaning of `Async` without an executor (default asynchronous execution facility) and `Async(..., Executor)` with an explicit executor.
7. Identify the risk of **blocking the completion thread**, increasing latency, and causing starvation/deadlock when callbacks perform blocking I/O or `join()`.
8. Understand how callback failure differs from source failure, propagation through dependent futures, and how to observe exceptions.
9. Design concise, non-blocking callbacks without placing dangerous side effects on an indeterminate thread; pass context intentionally rather than expecting `ThreadLocal` to propagate automatically.
10. Compile and run Java 17 to observe three different execution threads in controlled scenarios, without guessing via `Thread.sleep`.
11. Distinguish completion order from callback order, executor shutdown responsibilities, and relevant Java Memory Model guarantees.
12. Write tests based on **outcome invariants** rather than asserting that a non-`Async` callback always has a fixed thread name in production.

**Rule of thumb:** *no `Async` suffix* means the callback **is not requested to be dispatched asynchronously via an executor**. It may execute immediately on a thread participating in completion, including the thread calling the API when the source already has a result. *With the `Async` suffix* means the callback is dispatched via the default execution facility or the specified executor; it does not mean every stage in the pipeline runs on a newly created dedicated thread.

## 2. Why Does This Topic Matter?

An application creates a future to receive a result from the network or a thread pool. Then the code writes:

```java
CompletableFuture<Response> result =
        requestFuture.thenApply(this::parseAndValidate);
```

This is a snippet inside a method; `Response`, `requestFuture`, and `parseAndValidate` are defined by the application.

Beginners sometimes assume `parseAndValidate` always runs in a "background pool" because `requestFuture` is async. However, **that is not what `thenApply` promises**:

- If `requestFuture` is **not yet completed** when you register, the callback may be executed as soon as a thread completes the source, including a thread handling an I/O callback.
- If `requestFuture` is **already completed** before calling `thenApply`, the registration call may execute the function immediately **on the very thread calling `thenApply`**.
- If dependent completions interleave or multiple threads participate in completion, execution may occur on another participating thread per the JavaDoc policy.
- If the function is slow, whichever thread happens to execute it may be held up for a long time, even if the function never uses `synchronized`.

Consequence: looking at `thenApply(...)` alone is not enough to conclude "which thread the callback always runs on." You must understand **when the source completes**, **when the callback is registered**, and **the execution policy**.

## 3. From Future to CompletionStage

A `CompletableFuture<T>` is both a `Future<T>` whose result can be awaited/retrieved and an implementation of the `CompletionStage<T>` interface that allows declaring dependent actions.

Example:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> length =
        source.thenApply(String::length);
CompletableFuture<String> message =
        length.thenApply(n -> "length=" + n);
source.complete("hello");
System.out.println(message.join()); // length=5
```

Code snippet inside a method; requires importing `java.util.concurrent.CompletableFuture`.

- `source` is the source `CompletableFuture<String>`.
- `length` is a dependent stage transforming String → Integer.
- `message` further transforms Integer → String.
- `source.complete("hello")` marks the source as completed normally.
- Once the dependent actions finish, `message.join()` returns the expected string.

None of the methods here have `Async` in their name. The pipeline **does not request a new executor** for the transformations. The callbacks may run immediately when `source.complete` is called. For an already-completed source, they may run immediately when the new stage is created.

### Completion Differs from Execution

A future is a **representation of outcome state**, not necessarily a background thread/task itself:

- `new CompletableFuture<>()` creates an incomplete future **without starting a thread**.
- `complete(value)` sets the future's outcome if it is not yet complete, potentially triggering dependent actions.
- `supplyAsync(supplier, executor)` creates/submits an asynchronous computation to an executor.
- `thenApply(fn)` creates a dependent stage **without requesting** a new background task for the function.
- `thenApplyAsync(fn, executor)` creates a dependent stage and requests callback execution via the specified executor when the dependency is ready.

The distinction between "already having an asynchronous source" and "the dependent callback is also dispatched asynchronously" is the core concept of this article.

## 4. Execution Policy in Java SE 17

The `CompletableFuture` JavaDoc describes the policy for dependent completions **without an `Async` method**: these actions *may be performed by the thread that completes the current CompletableFuture, or by any other caller of a completion method*. In other words, Java **allows** the completing thread or a caller participating in completion to run the callback.

Key takeaways:

1. Do not assume the callback runs on the thread that **created the CompletableFuture**.
2. Do not assume the callback runs on the thread that **registered the callback**.
3. Do not assume the callback runs on **`ForkJoinPool.commonPool()`** if you did not call an `Async` method.
4. Do not assume the callback runs on **the same thread for every execution**.
5. Do not use the thread name as a business constraint unless you explicitly route the callback through an executor with an appropriate contract.
6. A callback may be executed **inline** within the `complete` call or within the callback registration call on an already-completed source. Therefore, the original call path may incur the callback's processing time.
7. Treat the callback's **thread safety and latency** like any code that could run on a thread owned by someone else.

The JavaDoc says **may**, not **must always**. That is why the examples below illustrate behavior **tested on Java 17**, while production decisions must be based on the execution policy rather than relying on a single timing.

## 5. Case A: Register First, Source Completes Later

```java
CompletableFuture<String> pending = new CompletableFuture<>();

CompletableFuture<String> observed = pending.thenApply(
        text -> Thread.currentThread().getName() + ":" + text);

Thread completer = new Thread(
        () -> pending.complete("ready"), "completer-thread");
completer.start();
completer.join();
System.out.println(observed.join());
```

This is a snippet inside a method that may `throws InterruptedException`; requires importing `CompletableFuture`.

- The `thenApply` callback is registered while `pending` is not yet done.
- The thread `completer-thread` calls `pending.complete("ready")`.
- In the common execution path of JDK 17, the completion thread runs the non-`Async` callback to complete `observed`.
- `completer.join()` waits for the completer thread to finish; `observed.join()` waits for the dependent stage to be done.
- When run on JDK 17 in the order above, the output is typically `completer-thread:ready`, as shown in the full tested example.

**Do not turn this into an assertion that every non-Async callback under all circumstances is executed by the exact thread calling `complete`.** Other callers/threads may participate in completion, especially in pipelines with multiple dependencies and races.

## 6. Case B: Source Already Completed Before Registration

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> observed = ready.thenApply(
        text -> Thread.currentThread().getName() + ":" + text);

System.out.println(observed.join());
```

This is a snippet inside a method. `ready` completed normally **before** `thenApply` was called. In the normal Java 17 implementation, the function runs **immediately on the thread calling `thenApply`** to produce the dependent outcome, rather than being dispatched to a worker automatically.

If the code is in `main`, the result is typically `main:ready`. If the code is processing an event-loop callback, the thread calling `thenApply` may be the event-loop thread itself, and the function may run right there.

### Why Does This Surprise Many Developers?

You may have an API returning a `CompletableFuture` that sometimes returns an already-ready cached result and sometimes needs the network:

- **Cache hit:** The Future is already complete. `thenApply` may execute immediately on the request-handling thread.
- **Cache miss:** The Future is not yet complete. `thenApply` may execute later on the thread that completes the I/O.

**The exact same line of source code** can cause the callback to run on two different kinds of threads depending on the data path. If the callback depends on thread affinity or performs blocking I/O, that difference creates hard-to-reproduce bugs.

## 7. Case C: Choosing an Explicit Executor with thenApplyAsync

```java
ExecutorService callbackPool =
        Executors.newSingleThreadExecutor(
                r -> new Thread(r, "callback-worker"));

try {
    CompletableFuture<String> ready =
            CompletableFuture.completedFuture("hello");

    CompletableFuture<String> processed =
            ready.thenApplyAsync(
                    text -> Thread.currentThread().getName()
                            + ":" + text.toUpperCase(),
                    callbackPool);

    System.out.println(processed.join());
} finally {
    callbackPool.shutdown();
}
```

This is a snippet inside a method; requires importing `CompletableFuture`, `ExecutorService`, and `Executors`. In production, shutdown/`awaitTermination` and policies for bounding queue/task duration are needed.

With a single-worker executor named `callback-worker`, the output in the normal execution path is `callback-worker:HELLO`. **An already-completed source** does not cause the function to run directly on the thread calling `thenApplyAsync`; the callback is dispatched via `callbackPool` per the API.

### Async Does Not Mean a New Thread

`Async` does not mean "create a new Thread for every callback." With a single-worker executor, multiple callbacks share that same worker. With `ForkJoinPool.commonPool()`, callbacks may use different common-pool workers. With a custom executor, resource/thread scheduling depends on the executor's configuration.

### Executor Rejection

If the executor is already shut down or rejects the task, the dependent stage may complete exceptionally with a rejection-related exception. `thenApplyAsync` does not guarantee that the callback will always run successfully. You must define executor ownership, lifecycle, and policy when capacity is exhausted.

## 8. Full Compiled and Run Java 17 Example

This program demonstrates **three execution contexts** and separates callback failure from source state:

1. Registering `thenApply` while the source is incomplete; a thread named `completer-thread` completes the source.
2. Registering `thenApply` on an already-completed source; the callback runs in the `main` thread of the Java 17 example.
3. Registering `thenApplyAsync` with an executor named `callback-worker`.
4. A callback intentionally throws `IllegalArgumentException`; the dependent fails while the source remains normal.

Create the file **`NonAsyncThreadDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NonAsyncThreadDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> earlyRegistration = pending.thenApply(
                s -> Thread.currentThread().getName() + ":" + s.toUpperCase());
        Thread completer = new Thread(() -> pending.complete("alpha"), "completer-thread");
        completer.start();
        completer.join();
        System.out.println("registeredBefore=" + earlyRegistration.join());

        CompletableFuture<String> ready = CompletableFuture.completedFuture("beta");
        CompletableFuture<String> lateRegistration = ready.thenApply(
                s -> Thread.currentThread().getName() + ":" + s.toUpperCase());
        System.out.println("registeredAfter=" + lateRegistration.join());

        ExecutorService callbackPool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "callback-worker"));
        try {
            CompletableFuture<String> explicitAsync = ready.thenApplyAsync(
                    s -> Thread.currentThread().getName() + ":" + s.toUpperCase(),
                    callbackPool);
            System.out.println("explicitAsync=" + explicitAsync.join());
        } finally {
            callbackPool.shutdown();
            if (!callbackPool.awaitTermination(5, TimeUnit.SECONDS)) {
                callbackPool.shutdownNow();
                throw new IllegalStateException("callback pool failed to stop");
            }
        }

        CompletableFuture<String> normalSource = CompletableFuture.completedFuture("bad");
        CompletableFuture<String> failed = normalSource.thenApply(s -> {
            throw new IllegalArgumentException("invalid value");
        });
        try {
            failed.join();
        } catch (CompletionException e) {
            System.out.println("callbackFailure=" + e.getCause().getClass().getSimpleName());
        }
        System.out.println("sourceStillNormal=" + !normalSource.isCompletedExceptionally());
    }
}
```

**Compile and run commands on JDK 17:**

```bash
javac --release 17 NonAsyncThreadDemo.java
java NonAsyncThreadDemo
```

**Exact tested stdout:**

```text
registeredBefore=completer-thread:ALPHA
registeredAfter=main:BETA
explicitAsync=callback-worker:BETA
callbackFailure=IllegalArgumentException
sourceStillNormal=true
```

### Explanation of Line 1

`earlyRegistration` is created while `pending` is incomplete. The thread named `completer-thread` calls `pending.complete("alpha")`, and JDK 17 in this example runs the `thenApply` callback on that thread. `Thread.currentThread().getName()` yields `completer-thread`, and `alpha.toUpperCase()` yields `ALPHA`.

### Explanation of Line 2

`ready` is created via `completedFuture("beta")`, so it is already done before `main` calls `thenApply`. In the observed execution, the function runs immediately on `main`, producing `main:BETA`.

### Explanation of Line 3

`thenApplyAsync` receives the explicit executor `callbackPool`. The ThreadFactory assigns the name `callback-worker`, so the callback runs there; `main` calls `join()` only to wait for the dependent completion, not to execute the callback.

### Explanation of Lines 4–5

`normalSource` has the normal outcome `"bad"`. The function of `failed` is invoked and throws `IllegalArgumentException`. The dependent `failed.join()` throws `CompletionException` wrapping that cause. However, `normalSource` remains completed normally; therefore `sourceStillNormal=true`.

**A common mistake:** thinking that "callback failed" also makes an already-succeeded source future fail. Each stage's outcome is independent. A dependent stage can fail due to the callback's own logic while upstream still holds a normal result.

### Stability of Sample Output

The sample deliberately controls ordering with `start/join` and `completedFuture`, and names the completer/executor threads for observation. The output above was tested on Java 17. In production applications, **do not assert fixed thread names for non-`Async` callbacks**; the execution policy allows multiple callers to participate in completion, and complex pipelines may behave differently from a small sample.

## 9. Comparison Table of Dependent Callback Types

| Method | Callback | Dependent Type | Requests Async Dispatch? |
|---|---|---|---|
| `thenApply(fn)` | `Function<T,U>` | `CompletableFuture<U>` | No |
| `thenApplyAsync(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Yes, default facility |
| `thenApplyAsync(fn, executor)` | `Function<T,U>` | `CompletableFuture<U>` | Yes, specified executor |
| `thenAccept(action)` | `Consumer<T>` | `CompletableFuture<Void>` | No |
| `thenAcceptAsync(action, executor)` | `Consumer<T>` | `CompletableFuture<Void>` | Yes |
| `thenRun(action)` | `Runnable` | `CompletableFuture<Void>` | No |
| `thenRunAsync(action, executor)` | `Runnable` | `CompletableFuture<Void>` | Yes |
| `thenCompose(fn)` | `Function<T,CompletionStage<U>>` | `CompletableFuture<U>` | No |
| `thenComposeAsync(fn, executor)` | `Function<T,CompletionStage<U>>` | `CompletableFuture<U>` | Yes |
| `whenComplete(action)` | `BiConsumer<T,Throwable>` | `CompletableFuture<T>` | No |
| `whenCompleteAsync(action, executor)` | `BiConsumer<T,Throwable>` | `CompletableFuture<T>` | Yes |
| `handle(fn)` | `BiFunction<T,Throwable,U>` | `CompletableFuture<U>` | No |
| `handleAsync(fn, executor)` | `BiFunction<T,Throwable,U>` | `CompletableFuture<U>` | Yes |

**The `Async` suffix applies to the callback of that specific stage**, and does not guarantee that every upstream/downstream stage in the chain is dispatched the same way. Each stage has its own execution policy.

### Non-Async Callback on `thenCompose`

`thenCompose` takes a function that returns another stage and **flattens** the result. The function may run inline under the non-Async policy, while the stage returned by the function may complete at an entirely different time and on a different thread. Thus, `thenCompose` neither turns all I/O inside the new future into synchronous execution nor guarantees that the function runs on a background thread.

## 10. An Async Source Does Not Make Subsequent Callbacks Run Async

Code snippet:

```java
ExecutorService ioExecutor = Executors.newFixedThreadPool(4);
CompletableFuture<Payload> fetched =
        CompletableFuture.supplyAsync(() -> fetchRemote(), ioExecutor);

CompletableFuture<View> mapped =
        fetched.thenApply(this::toView);
```

This is an illustrative snippet inside a method; `Payload`, `View`, `fetchRemote`, and `toView` are defined by the application. When `fetched` is not yet complete at registration time, `toView` may run on the worker in `ioExecutor` that completes the supplier. If `fetched` is already completed, `toView` may run immediately on the thread registering the callback.

**`supplyAsync` creates an asynchronous source; `thenApply` is a non-Async dependent.** There is no rule that "every stage after `supplyAsync` uses `ioExecutor`." To dispatch the callback via an executor of your choice, write:

```java
CompletableFuture<View> mapped =
        fetched.thenApplyAsync(this::toView, mappingExecutor);
```

Illustrative snippet; `mappingExecutor` is created and owned by the application. Distinguish between the I/O pool, the CPU processing pool, the event-loop pool, and where continuations run.

## 11. A Callback on an Already-Completed Source May Run Immediately During Registration

If `source` is already completed, the snippet:

```java
long start = System.nanoTime();
CompletableFuture<String> result =
        source.thenApply(this::expensiveTransformation);
long spentNanos = System.nanoTime() - start;
```

is an illustrative snippet; `source` and `expensiveTransformation` are defined by the application.

`spentNanos` may include nearly the entire transformation time because the callback runs inline. Do not conclude that `thenApply` is a method that "only registers and never does work." This is a common cause of unexpected latency on HTTP request threads or UI event loops.

If the source completes via a cache hit, a heavy `thenApply` can immediately occupy the caller; on a cache miss, the same function occupies the completion thread instead. A performance bug may manifest inconsistently depending on the cache hit ratio.

**Proper design:** if a transformation is heavy or requires thread affinity, use `thenApplyAsync(..., properExecutor)` instead of hoping the source is not yet complete.

## 12. A Callback on the Completer Thread Can Slow Down complete()

Consider the code:

```java
CompletableFuture<Integer> pending = new CompletableFuture<>();
pending.thenApply(value -> {
    heavyCpuTask(value);
    return value + 1;
});
pending.complete(10);
```

This is a snippet inside a method; `heavyCpuTask` is defined. Because a non-`Async` action can execute immediately on the thread calling `pending.complete`, the `complete(10)` call may have to execute `heavyCpuTask` before returning in the corresponding executions.

This affects:

- **Latency:** the thread emitting the completion event is held up for a long time.
- **Throughput:** an I/O completion thread may spend time doing the callback's CPU computation.
- **Fairness:** a source with many heavy dependent callbacks can force a thread participating in completion to process a long chain.
- **Backpressure:** if the completion thread must also receive more events, its queue backs up.
- **Thread affinity:** the callback may run on a thread unsuitable for blocking or UI operations.

You do not need a "new thread" to have asynchrony at the source stage; however, choosing *where callbacks run* must be designed separately.

## 13. When to Use Async and When Not To

### Usually Suitable for Non-Async

- Very fast, pure transformations: `String::trim`, enum conversion, extracting a field from an immutable object.
- Lightweight mapping/validation, no blocking I/O, no holding large locks.
- Operations requiring no thread affinity.
- Acceptable for the callback to run inline/on caller/on completer because execution time is small and predictable.
- Preferring to avoid queue/dispatch overhead when workloads are tiny.

### Usually Suitable for Async with an Explicit Executor

- CPU-heavy mapping that needs to be routed to a compute pool.
- Blocking I/O or high-latency operations routed to an appropriate pool.
- Sending logs/metrics/side tasks without blocking the source completion thread.
- Code that must run on a dedicated event loop/GUI thread represented by an executor.
- Isolating components with different resources and SLAs.
- Needing control over queue capacity, rejection policy, worker names, monitoring, and lifecycle.

### Async Does Not Guarantee Everything Automatically

`thenApplyAsync` does not automatically make a non-thread-safe callback thread-safe, does not create transactions over external state, does not prevent concurrent execution with other callbacks, and does not automatically prevent deadlocks when a callback blocks waiting for a task with no available worker.

There is scheduling/queueing overhead; if each transformation takes only a few nanoseconds, dispatching Async separately can cost more than the computation itself. Choose a policy based on correctness/latency and measure under realistic load.

## 14. What Is the Default Asynchronous Execution Facility?

In Java 17 `CompletableFuture`, `Async` methods **without an Executor parameter** typically use the default asynchronous execution facility, usually `ForkJoinPool.commonPool()` when parallelism requirements are met per the JavaDoc. In some cases, the runtime uses a new thread per task if the common pool does not support sufficient parallelism as defined by the implementation.

Important points:

- Do not hard-code the thread name of default Async.
- Do not assume the thread running the callback is the thread that called `thenApplyAsync`.
- If the workload is heavily blocking, the common pool may not be the right place.
- Do not arbitrarily shut down the common pool as you would an application-created executor.
- If isolation or an explicit policy is needed, pass an `Executor` to the `Async` overload.
- Do not rely on "Async always creates a new thread"; the common pool normally reuses workers.

### Example with an Explicit Executor

```java
ExecutorService computePool = Executors.newFixedThreadPool(4);
CompletableFuture<String> source =
        CompletableFuture.completedFuture("hello");
CompletableFuture<String> mapped =
        source.thenApplyAsync(String::toUpperCase, computePool);
```

This is an illustrative code snippet inside a method; imports `CompletableFuture`, `ExecutorService`, `Executors`. `computePool` should be closed according to its owner's lifecycle after tasks complete; the snippet omits shutdown to focus on the execution policy.

## 15. Non-Async Callbacks in Multi-Stage Pipelines

Consider:

```java
CompletableFuture<String> result = source
        .thenApply(this::parse)
        .thenApply(this::normalize)
        .thenApply(this::render);
```

This is an illustrative snippet inside a method, requiring compatible methods.

If `source` is not yet done and a thread calls `source.complete(...)`, multiple non-`Async` continuations may run on the same thread participating in completion. This is a **permitted possibility**, not a fixed guarantee for every chain/contention state.

A heavy callback in the middle can lengthen the completion path and delay other callbacks. If you want to isolate the CPU-intensive step:

```java
CompletableFuture<String> result = source
        .thenApply(this::parse)
        .thenApplyAsync(this::normalize, cpuExecutor)
        .thenApply(this::render);
```

This is an illustrative snippet; `cpuExecutor` is defined by the application. `normalize` is dispatched to `cpuExecutor`. The non-Async `render` may then run on the thread that completes `normalize` or another thread participating in completion later—it is not guaranteed to "return to main."

**An Async stage in the middle does not give subsequent stages fixed executor affinity.** If `render` must run on a UI thread, continue using `thenApplyAsync(..., uiExecutor)` for the render stage.

## 16. Sibling Callbacks Have No Ordering Guarantee

If you register multiple callbacks on a single source:

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.thenAccept(v -> log("A:" + v));
source.thenAccept(v -> log("B:" + v));
source.complete("done");
```

This is a snippet; `log(String)` is defined by the application. **Do not use the order of appearance in source code to assume "A is called before B."** `CompletableFuture` does not provide transactional ordering for independent sibling continuations in exact registration order that an application can rely on in all circumstances.

If B must run after A, create an explicit dependency:

```java
CompletableFuture<Void> ordered =
        source.thenAccept(v -> log("A:" + v))
              .thenRun(() -> log("B:done"));
```

This is an illustrative code snippet inside a method. The `thenRun` stage depends on the normal completion of the previous stage, thereby establishing logical ordering rather than relying on scheduling order between siblings.

In particular, **callback thread identity** and **callback execution order** are two independent aspects: two actions may run on the same thread without any guaranteed registration order, or on different threads if `Async` is used.

## 17. thenApply(), thenAccept(), thenRun(): Similarities and Differences

| Method | Callback Receives | Callback Returns | Dependent Type | Can Inline When Non-Async? |
|---|---|---|---|---|
| `thenApply(fn)` | Value T | U | `CompletableFuture<U>` | Yes |
| `thenAccept(action)` | Value T | void | `CompletableFuture<Void>` | Yes |
| `thenRun(action)` | No value | void | `CompletableFuture<Void>` | Yes |

Example:

```java
CompletableFuture<Integer> number =
        CompletableFuture.completedFuture(10);

CompletableFuture<Integer> doubled =
        number.thenApply(n -> n * 2);
CompletableFuture<Void> recorded =
        doubled.thenAccept(n -> record(n));
CompletableFuture<Void> notified =
        recorded.thenRun(() -> notifyDone());
```

This is a snippet with `record` and `notifyDone` defined. The callbacks are all non-`Async`; because the source is already completed, they may run immediately on the registering thread in JDK 17, without defaulting to a new pool.

**If a side-effect callback is important**, do not ignore the `recorded` or `notified` stage. You need to join/get/handle exceptions of the corresponding dependent, because `number` succeeding does not prove that the record/notify operation succeeded.

## 18. thenCompose() and the Difference Between "Executing the Function" and "Waiting for the Child Future"

`thenCompose` maps a value to another `CompletionStage<U>` and then flattens it:

```java
CompletableFuture<User> fetched = lookupUserAsync(userId);

CompletableFuture<Profile> profile =
        fetched.thenCompose(user -> lookupProfileAsync(user.id()));
```

This is a snippet inside a method, with `User`/`Profile`/`lookupUserAsync`/`lookupProfileAsync` defined by the application.

Two separate concerns:

- **The Function** `user -> lookupProfileAsync(...)` is the callback of `thenCompose`. Because it is non-`Async`, this Function may run inline on the thread completing `fetched` or on the caller.
- **The child Future** returned by `lookupProfileAsync` may be an asynchronous computation completing on a different thread at a different time. `thenCompose` **does not block waiting** for it like `join`; the dependent stage awaits the outcome via composition.

If the function contains heavy code before returning the Future, it can still block the completer/caller. If the function only creates/submits an async operation and returns immediately, the heavy work may reside on that operation's own executor.

`thenComposeAsync(fn, executor)` changes **where the Function is dispatched**, not the execution thread of all internal operations created by the Function itself.

## 19. whenComplete(), handle(), and exceptionally(): Callbacks on Failure

Ordinary `thenApply`/`thenAccept` callbacks only run their function when the source stage completes normally. When the source stage completes exceptionally, the dependent typically completes exceptionally **without invoking the Function on a nonexistent value**.

To observe errors, use `whenComplete` or `handle`:

```java
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });

CompletableFuture<String> recovered = observed.exceptionally(
        error -> "fallback");
```

This is a snippet; `recordFailure(Throwable)` is defined by the application. `whenComplete` is an observational action receiving both value and error, typically preserving the previous outcome if the action itself completes normally. `exceptionally` lets you convert a failure into a fallback value.

### Execution Policy Still Applies

A non-`Async` `whenComplete` may run on the completer or caller just like `thenApply`. If logging inside `recordFailure` blocks for several seconds, the completion thread may be tied up. Use `whenCompleteAsync(..., loggingExecutor)` if separate dispatch is needed, while still avoiding executor backlog.

`handle(fn)` transforms both success and failure into a new result, whereas `exceptionally(fn)` only handles exceptional completion. They have their own variants; do not equate them with `Thread` exception handlers or a `try/catch` wrapping the registration call.

### Callback Throwing an Exception Itself

In the demo, the source completed normally and `thenApply` threw `IllegalArgumentException`, causing the dependent to fail. With `whenComplete`, if the action throws a new exception, the outcome depends on whether the source already failed and the `CompletionStage` contract; do not assume telemetry callbacks are always harmless. Design logging/metrics to be exception-safe so they do not mask the original failure or unexpectedly fail the observed stage.

## 20. Source Exceptions Differ from Dependent Exceptions

Model:

```text
                 SOURCE CompletableFuture<T>
                       /           \
               completed OK     completed FAIL
                    |                |
                thenApply fn       fn does not run
                  /    \                |
            fn return  fn throw     dependent FAIL
              |          |
       dependent OK   dependent FAIL
```

A `CompletableFuture` that has already completed does not have its "state rewritten" just because a dependent action failed. Each stage has its own completion state.

### Observing Exceptions

`join()` on a failed dependent typically throws `CompletionException` with the root cause; `get()` throws `ExecutionException` with the cause. `CancellationException` has its own semantics if the stage was canceled.

```java
try {
    result.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    report(cause);
}
```

This is a snippet; `result` and `report` are defined. If cancellation is permitted, handle `CancellationException` separately; do not lump cancellation into business failures regardless of context.

### Source completeExceptionally

`source.completeExceptionally(error)` makes the source fail. If `thenApply(fn)` depends on it, the function is not run normally with a value; the dependent receives the exceptional completion. However, if `handle`/`whenComplete` is used, the error-handling callback may run (and is still subject to the non-Async execution policy).

## 21. Non-Async Callbacks and ThreadLocal Context

`ThreadLocal` stores data **bound to a thread**, not to a logical request or a `CompletableFuture`. A pipeline may run a callback on the completer thread or the registering thread depending on timing, so `ThreadLocal` context does not propagate automatically and reliably.

Error-prone example:

```java
ThreadLocal<String> traceId = new ThreadLocal<>();
traceId.set("request-123");

CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> traced =
        source.thenApply(value -> traceId.get() + ":" + value);
```

This is a snippet inside a method. If another thread calls `source.complete("ok")`, the callback may run on that thread, where `traceId.get()` is `null` or a leftover value from another request if a pooled thread was not cleaned up.

**Do not fix this by claiming non-Async always runs on the caller.** That assumption itself is wrong.

### Better Strategies

- Pass context as an immutable value in the data flow, e.g., `record Contextual<T>(String traceId, T value)`.
- Or capture the context at registration time and wrap the callback to set/restore `ThreadLocal` **inside a `try/finally`** when integration with a `ThreadLocal`-based library is required.
- Do not hold large references or credentials in `ThreadLocal` longer than the callback's duration.
- In thread pools, remember to clean up/restore context to avoid leaking into the next task.
- `Async` with a dedicated executor also **does not propagate `ThreadLocal` automatically**; thread affinity and context propagation are two separate concerns.

If a specific UI/event-loop thread is required, use the executor provided by the UI framework and do not wait blocking on that event loop. Keep Spring-specific context out of scope for this article.

## 22. Non-Async Callbacks and Blocking I/O

The most dangerous part of non-`Async` callbacks is blocking operations:

```java
CompletableFuture<String> response = readNetworkAsync();

CompletableFuture<String> audited = response.thenApply(value -> {
    writeAuditToDatabase(value); // May block.
    return value;
});
```

This is an illustrative snippet; `readNetworkAsync` and `writeAuditToDatabase` need to be defined.

If the I/O completion thread calls `response.complete`, the callback may **execute database I/O right on that thread**. If that thread also needs to handle other network events, it can become congested.

If the callback is registered when the source is already complete, the request thread calling `thenApply` itself may be blocked. Thus, latency bugs can vary by cache hit/miss or race timing.

### One Way to Fix It

```java
CompletableFuture<String> audited = response.thenApplyAsync(
        value -> {
            writeAuditToDatabase(value);
            return value;
        },
        auditExecutor);
```

This is a snippet; `auditExecutor` is owned by the application, needs its own capacity/queue/timeout, and must not be placed on a UI thread. However, merely moving blocking I/O to an executor **does not automatically create a transaction** between the audit and the source result; exceptions and retry/idempotency must still be handled if needed.

### Do Not Dump Every Callback into the Common Pool

If a callback can block for a long time, an executor dedicated to blocking I/O is usually more appropriate than the default common pool shared by many other computations. Still, avoid creating unbounded pools that cause exhaustion; monitor queue depth, task duration, rejections, and cleanup.

## 23. Thread Starvation Deadlock with a Single Worker

A design example that can deadlock:

```java
ExecutorService oneWorker = Executors.newSingleThreadExecutor();

CompletableFuture<String> outer = CompletableFuture.supplyAsync(() -> {
    CompletableFuture<String> inner =
            CompletableFuture.supplyAsync(() -> "inner", oneWorker);
    return inner.join(); // Waits for a task queued on the same oneWorker.
}, oneWorker);
```

This is a **dangerous illustrative snippet**; do not run without a timeout in production. `outer` uses the single worker. While the lambda runs, it enqueues `inner` onto the same executor and then calls `join()`. `inner` cannot start because the worker is occupied by `outer` waiting. This is a **thread-starvation deadlock**.

A similar circular dependency can occur in a non-Async callback if the callback runs on the completing worker and waits on a stage that requires that very same worker.

### Fix with Composition, Not Blocking Join

```java
CompletableFuture<String> outer =
        CompletableFuture.completedFuture("start")
                .thenCompose(value ->
                        CompletableFuture.supplyAsync(
                                () -> "inner", oneWorker));
```

This is a snippet with `oneWorker` already created. `thenCompose` returns a dependent that awaits the child future **by composition**, without occupying the worker just to block at `join`. Not every deadlock disappears with `thenCompose` if the inner code still has locks or circular dependencies, but it resolves the "worker waiting on a task in its own pool" pattern in this example.

## 24. Callback Execution Can Differ from Business Semantics

Suppose a dependent stage `thenApply` converts JSON into a DTO. You want:

- The DTO to match the schema.
- Exceptions to propagate completely.
- No context leakage between requests.
- No blocking of the I/O completion thread.
- Execution in a CPU pool to bound load.

**Getting the right result is not enough.** You must also choose the right callback scheduling to protect latency, fairness, and resource isolation.

Conversely, if the function is just `x -> x.id()` on an immutable object taking a few nanoseconds, adding an executor hop can introduce overhead without improving correctness. A non-Async callback may be a good choice.

### Analysis by Requirement

| Requirement | Typical Choice |
|---|---|
| Ultra-lightweight, pure mapping | `thenApply` |
| CPU-heavy mapping | `thenApplyAsync(fn, cpuExecutor)` |
| Callback must run on an event loop | `thenAcceptAsync(action, eventLoopExecutor)` with an executor genuinely representing the event loop |
| Blocking DB audit | `thenApplyAsync(fn, boundedIoExecutor)` or an async I/O model with completion |
| Fast error observation only | `whenComplete` with non-blocking telemetry |
| Potentially slow logging | `whenCompleteAsync(..., loggingExecutor)` or a bounded queue |
| Stage returning another Future | `thenCompose` or `thenComposeAsync` depending on function cost/affinity |
| Callback needs caller context | Explicit capture/propagation; do not expect `ThreadLocal` to follow automatically |

Choosing the right executor still requires managing lifecycle, deadlines, and exceptions. Thread affinity does not replace correctness for shared data.

## 25. Completion Race: Who Is Allowed to Run the Callback?

When a source is about to complete, thread T1 may call `complete` while thread T2 is registering a callback. Some valid schedules:

```text
Schedule A:
  T2: register thenApply while source incomplete
  T1: complete(source) -> executes dependent action

Schedule B:
  T1: complete(source)
  T2: thenApply on already-complete source -> executes action inline

Schedule C:
  T1/T2 both participate in completion or multiple dependent stages
  callback may be executed by another thread participating in completion
```

A sound design does not depend on which schedule occurs:

- The function does not misuse implicit `ThreadLocal`.
- The function does not block sensitive threads if policy does not guarantee it.
- The function is thread-safe if it can run concurrently with other callbacks.
- The dependent outcome is read via `join()/get()` or a handler when needed.
- Side effects/metrics do not rely on the thread name as a business identity.
- Cancellation and timeouts are not inferred from thread location.

### Do Not Assume a Callback Always Runs "Once Per complete Call"

Multiple threads may race to call `complete` on a `CompletableFuture`; only one outcome wins. A stage's dependent action is governed by the completion protocol, not re-run once per `complete` attempt. However, if you register **two independent dependents** with the same side-effecting function, those are two separate stages and the side effect may be executed twice by design.

## 26. Cancellation Is Not the Same as Interrupting the Callback Thread

`CompletableFuture.cancel(true)` completes the future with cancellation if it is still pending, but the JavaDoc states that the `mayInterruptIfRunning` parameter **has no effect on controlling interruption** in the `CompletableFuture` implementation.

- Canceling the source can cause dependents to complete exceptionally.
- Canceling a dependent does not by default cancel the source.
- Canceling a dependent does not guarantee stopping a callback already executing on the completer thread.
- If the callback is blocking I/O, you need the actual I/O's deadline/cancellation handle.
- If a source is already complete, `cancel` typically does not change the outcome.
- `isDone()` being true covers normal, exceptional, and canceled completions.
- A `whenComplete` callback may need to distinguish `CancellationException` from business errors.

**Do not use `cancel(true)` as a guaranteed way to interrupt a stalled thread inside `thenApply`.** Distinguish Future completion state from execution control of the underlying task.

## 27. Timeouts and the Difference Between get(timeout) and orTimeout

`result.get(100, TimeUnit.MILLISECONDS)` may throw `TimeoutException` to **the waiting thread**, but does not complete `result` itself and does not stop the callback.

`result.orTimeout(100, TimeUnit.MILLISECONDS)` schedules **that future itself** to complete exceptionally with `TimeoutException` if not completed by the deadline, but does not automatically interrupt the underlying callback/HTTP request.

`result.completeOnTimeout(defaultValue, 100, TimeUnit.MILLISECONDS)` can complete normally with a fallback value upon expiration.

These are distinct semantics:

| API | Primary Effect | Automatically Cancels Actual I/O? |
|---|---|---|
| `get(timeout, unit)` | Bounds caller wait | No |
| `orTimeout(timeout, unit)` | Future may fail due to timeout | No |
| `completeOnTimeout(value, ...)` | Future may complete with fallback | No |
| `cancel(...)` | Future marked canceled | Not guaranteed to stop underlying work |

If a non-Async callback runs for a long time on a completion thread, the future timeout may have already fired while the work continues. Design deadlines on the I/O/task itself, not just the Future handle.

## 28. Java Memory Model and Visibility Relationships

`CompletableFuture`/`Future` provides mechanisms to publish results and await completion, but **which thread executes the callback** does not by itself determine whether mutable data is safe.

Example where result data is created in one thread and then the future completes:

```java
record Payload(int id, String value) {}

CompletableFuture<Payload> result = new CompletableFuture<>();
// In another producer thread:
result.complete(new Payload(42, "ready"));
// In the callback:
result.thenApply(payload -> payload.id());
```

This is multithreaded pseudocode using a Java 17 record. Future publication/consumption has appropriate memory ordering so the callback can use data created before completion per the API. An immutable record helps avoid subsequent races.

### What Is Not Guaranteed

- Multiple callbacks mutating a shared `int counter++` can still suffer lost updates; use `AtomicInteger`, locks, or ownership.
- `thenApply` does not automatically create a monitor lock around domain data.
- A callback running on the same thread in one execution does not prove it will always run on the same thread later.
- `Thread.sleep` does not establish a valid happens-before relationship to publish mutable state.
- Mutable data that another thread continues to modify after the Future completes requires separate synchronization.
- Completion of a Future does not automatically synchronize with an external database transaction or network acknowledgment.

### Use join/get in the Right Role

`dependent.join()`/`get()` waits for the dependent stage to complete. If you want to know that **the callback has finished running**, wait on the dependent, not just the source. A source being done does not prove that an `Async`-dispatched callback has finished.

In the example, `main` calls `explicitAsync.join()` to wait for the callback on `callback-worker`. Reading the source `ready.join()` only tells you the source succeeded earlier; it says nothing about the new callback.

## 29. Observability: Tracking Callback Thread and Duration

To detect callbacks that hold a completion thread for too long:

- Log **stage name/correlation id**, not just the thread name.
- Record callback timing and end-to-end latency.
- Monitor executor queue/rejections when using `Async(..., executor)`.
- Use JFR (Java Flight Recorder) for appropriate events, and thread dumps when starvation/blocking is suspected.
- When logging, separate source failures from callback failures.
- Do not log sensitive payloads or secrets from context.
- Avoid heavy logging inside the callback being measured; instrumentation itself can cause latency.
- If there is a UI/event loop, monitor for blocked event loops as a warning sign of misplaced non-Async usage.

Use `System.nanoTime()` for measuring duration, not wall-clock time, to accurately compare very short intervals.

Lightweight instrumentation example:

```java
CompletableFuture<String> measured = source.thenApply(value -> {
    long start = System.nanoTime();
    try {
        return transform(value);
    } finally {
        observeNanos(System.nanoTime() - start);
    }
});
```

This is a snippet; `transform`/`observeNanos` are defined by the application. `observeNanos` must be brief and exception-safe so it does not accidentally fail the dependent. If `transform` throws, `finally` still runs to record the duration.

## 30. Testing Correctly Instead of Asserting Unpromised Thread Affinity

### Testing Outputs and Exceptions

Use `CompletableFuture.completedFuture` for normal input, `completeExceptionally` for failed input, and `join()/get()` to assert outcomes. This is stable and independent of the thread scheduler.

### Testing to Illustrate Policy

The demo deliberately names the completer/executor to illustrate execution on Java 17. In documentation tests like that, you can assert thread names in a controlled environment, but **do not turn that output into a contract across all pipelines/implementations**.

### Testing Heavy Callbacks

If you need to prove a callback does not block a sensitive thread, the best option is to **pass an executor with a clear contract** and use a thread factory/metric to verify; do not try to force a non-Async callback to always run on a worker using sleep.

### Testing Concurrency

Use `CountDownLatch` to control when the source completes and when the callback is registered if you want to reproduce a race. Do not rely on `Thread.sleep(100)` to ensure thread A registered before thread B.

### Testing Shutdown

For `thenApplyAsync(..., executor)` owned by the application, test shutdown/rejection policies and ensure callers have deadlines. A code path that only tests the "happy path" without testing executor shutdown can fail in production.

## 31. Common Mistakes

1. **"`thenApply` always runs on a background thread."** False; it may run on the completer or caller.
2. **"A source created with `supplyAsync` makes the whole chain Async by default."** False; non-`Async` `thenApply` follows its own policy.
3. **"Registering a callback only stores the function and never runs it immediately."** False if the source is already complete; the callback may run inline.
4. **"A non-Async callback always runs on the thread calling `complete`."** False; the JavaDoc allows other callers to participate in completion.
5. **"A non-Async callback always runs on the thread that created the source."** False; creation does not confer thread ownership.
6. **"A non-Async callback always runs on the registering thread."** False if the source is incomplete and another thread completes it.
7. **"`thenApplyAsync` creates a new thread every time."** No; executors normally reuse workers.
8. **"`thenApplyAsync` always uses the previous `supplyAsync`'s executor."** No; if unspecified, it uses the stage's default async facility.
9. **"One Async stage makes all subsequent stages Async."** False; each stage has its own execution policy.
10. **"Using `ThreadLocal` in a callback will have the request's context."** Not guaranteed; context must be propagated intentionally.
11. **"Blocking I/O in `thenApply` does not affect the completion producer."** False; the function may run inline during completion.
12. **"A heavy callback on the cache-hit path still won't affect the caller."** False; an already-ready source can make the callback run immediately.
13. **"Callbacks registered first will run in exact registration order."** There is no sibling callback ordering that business code should rely on.
14. **"A callback throwing turns an already-succeeded source into failed."** False; the dependent fails while the source keeps its own outcome.
15. **"`source.join` waits for all dependent Async callbacks."** No; you must wait on the specific dependent.
16. **"`whenComplete` without Async is always lightweight."** The API does not restrict callback code; the developer must ensure it.
17. **"Canceling a CompletableFuture will interrupt the callback thread."** Not guaranteed.
18. **"Timeout on `get` automatically stops the callback."** No; it only stops the caller from waiting.
19. **"Using `join` inside a worker of the same single-thread pool is always safe."** Can cause thread-starvation deadlock.
20. **"`thenCompose` blocks waiting for the child Future like `join`."** No; composition connects stages without a blocking join.
21. **"Non-Async callbacks never race concurrently with each other."** Siblings/dependencies can run on multiple threads; shared mutable state still needs synchronization.
22. **"Async solves every thread-safety issue."** Async only changes dispatch, not data ownership.
23. **"Async is always faster than non-Async."** No; dispatch overhead and queue delay can outweigh a tiny callback.
24. **"Creating a new executor per request is harmless."** Prone to thread/resource leaks without ownership/shutdown.
25. **"Thread name indicates business request identity."** No; threads are reused and callbacks can migrate per completion policy.
26. **"Future done means all external side effects committed."** No; explicit acknowledgment/transaction is needed.
27. **"A callback can freely log secrets because it's on the backend."** No; telemetry must still comply with privacy/security.
28. **"A UI callback using non-Async `thenAccept` is always UI-thread-safe."** False; the callback may run on a worker.
29. **"Caller's `ThreadLocal` is automatically copied to `thenApplyAsync`."** No; it must be propagated.
30. **"All callback threads are managed by the source executor."** False; threads participating in completion and explicit callback executors may differ.

## 32. Checklist When Reviewing CompletableFuture Code

Before merging a Java 17 pipeline:

- **Stage ownership:** where is the source created/run and who completes it?
- **Registration timing:** can the callback be registered before or after the source completes?
- **Execution policy:** does the callback use non-Async, default Async, or an explicit Executor?
- **Thread affinity:** does the callback require a specific UI/event-loop/CPU/I/O thread?
- **Cost:** does the callback have blocking I/O, CPU-heavy compute, lock contention, or synchronous logging?
- **Data safety:** does the callback mutate unprotected shared state?
- **ThreadLocal:** does context need explicit propagation and cleanup?
- **Chaining:** is logical order expressed via dependent stages rather than sibling registration order?
- **Failure:** are source and callback exceptions observed distinctly?
- **Completion:** does the caller wait on the source or the dependent, with a timeout where needed?
- **Cancellation:** does canceling the future actually cancel the underlying operation?
- **Pool capacity:** does the executor have enough workers for dependencies that need to make progress?
- **Rejection/shutdown:** can an Async callback be rejected when the executor stops accepting work?
- **Observability:** are callback latency and source completion latency measured separately?
- **Resource ownership:** who creates the executor and who shuts it down?
- **Testing:** have incomplete source, already-complete source, callback throwing, async executor, and timeout been tested?
- **Special scope:** does the problem strictly stay within Java concurrency without mixing in out-of-scope framework-specific scheduling?

## 33. Review Questions and Answers

**Q1.** Is non-Async `thenApply` guaranteed to run on the thread calling `thenApply`?  
**Answer:** No. If the source is not yet complete, the callback may run on the thread completing the source; if the source is already complete, it may run inline on the caller in Java 17.

**Q2.** Is `thenApply` guaranteed to run on the completer thread?  
**Answer:** Not strictly. The JavaDoc allows the completing thread or callers participating in completion, depending on races/implementation.

**Q3.** Why can the same code have different latency on cache hit vs. cache miss?  
**Answer:** A cache hit has an already-completed future so a non-Async callback may run immediately on the caller; a cache miss may run later on the thread completing I/O.

**Q4.** A `supplyAsync` source uses executor A; does a subsequent `thenApply` use executor A by contract?  
**Answer:** No. A non-Async callback has no executor affinity. It may run on the thread completing A or a caller participating in completion.

**Q5.** If you want a CPU-heavy callback to run in pool B, what should you use?  
**Answer:** `thenApplyAsync(fn, poolB)` with pool B properly configured and lifecycle-managed.

**Q6.** Does `thenApplyAsync(fn)` without an executor definitely run on a new thread?  
**Answer:** No; it typically uses the default asynchronous execution facility such as the common pool, which can reuse workers.

**Q7.** If a `thenApply` callback throws a `RuntimeException`, is the already-succeeded source still successful?  
**Answer:** Yes; the dependent stage fails, while the source outcome remains unchanged.

**Q8.** Should you call `source.join` or `dependent.join` to ensure an Async callback has finished?  
**Answer:** Wait on `dependent.join`/get; the source being done does not prove the dependent callback has completed.

**Q9.** Do `thenAccept` and `thenRun` share the same non-Async policy?  
**Answer:** Yes: without `Async`, the callback may execute inline on a thread participating in completion; they differ in whether they receive a value.

**Q10.** Does `thenCompose` wait on the child future using a blocking `join`?  
**Answer:** No. It flattens a returned stage, allowing composition without a blocking join.

**Q11.** Should you put a slow database call inside `thenApply` when the source may complete on an I/O event loop?  
**Answer:** Usually no; the callback can block the event loop. Use an asynchronous I/O API or an appropriate explicit bounded executor.

**Q12.** Is the registering thread's `ThreadLocal` context automatically propagated to the completer callback?  
**Answer:** No. Explicit propagation and restore/cleanup are required.

**Q13.** Do two `thenAccept` siblings always run A before B in registration order?  
**Answer:** Not guaranteed. If ordering is needed, chain `thenAccept(...).thenRun(...)`.

**Q14.** Does `cancel(true)` on a `CompletableFuture` guarantee interrupting the underlying callback?  
**Answer:** No. You must handle cancellation separately for the underlying task if you want to stop it.

**Q15.** Does `orTimeout` guarantee canceling a network request?  
**Answer:** No; it changes the future's completion state at the deadline, while the underlying operation needs its own timeout/cancellation.

**Q16.** Which thread name should you assert for a non-Async callback in production?  
**Answer:** Do not assert a fixed name if the API does not guarantee one; test correctness and use an explicit executor if thread affinity is a requirement.

**Q17.** Does non-Async mean the callback always executes synchronously before the registration method returns?  
**Answer:** No. If the source is still incomplete, the callback may execute later; if the source is already complete, it may run inline.

**Q18.** Can one non-Async callback run on the thread calling `complete` while another runs on the thread calling `thenApply`?  
**Answer:** Yes, due to different timing of each source/stage and completion registration.

**Q19.** When using `thenApplyAsync`, do you need to shut down a self-created executor?  
**Answer:** Yes, if the application owns the executor and there is no other lifecycle manager. Pending callbacks and a graceful shutdown policy must be managed.

**Q20.** Does dispatching a callback via an explicit executor mean external systems also get an exactly-once transaction?  
**Answer:** No; callback scheduling and atomicity of external side effects are two independent concerns.

## 34. Practice Exercises

### Exercise A — Before/After Completion

Write two independent tests: test 1 registers `thenApply` while the source is still pending and a named thread completes it; test 2 creates `completedFuture` and registers the callback on `main`. Record the thread names, explain why both fall under the permitted execution policy, and do not turn thread names into a production contract.

### Exercise B — Async Executor

Create an `ExecutorService` with a custom `ThreadFactory` name, then use `thenAcceptAsync`. Assert the callback finishes before `main` reads the result, manage shutdown, and test when the executor is already shut down.

### Exercise C — Source Success, Dependent Failure

Create `CompletableFuture.completedFuture("bad")`; `thenApply` validates the data and throws. Verify `source.isCompletedExceptionally()==false`, `dependent.isCompletedExceptionally()==true`, and `join` on the dependent has the expected cause.

### Exercise D — Single-Worker Deadlock

Write a test harness with a timeout for the case where a supplier in a single-thread pool calls `join` on another task submitted to the same pool. Explain why the tasks make no progress, then refactor using `thenCompose` without a blocking join inside the worker.

### Exercise E — Context Propagation

Have a non-Async callback read a `ThreadLocal`. Complete a source on another worker and observe that the value is not propagated. Fix it by capturing immutable context and passing it into the callback; if a real `ThreadLocal` is required, set/restore it in `finally`.

### Exercise F — Heavy Callback

Try `thenApply` with an expensive mapping on a completed source, and measure how long the thread calling `complete` or `thenApply` can be occupied. Switch to `thenApplyAsync(..., cpuExecutor)`, re-measure caller/completer latency and total end-to-end latency. Do not conclude Async is "always faster"; measure queueing overhead as well.

### Exercise G — Callback Ordering

Register two `thenAccept` siblings on the same source, then replace them with a `thenAccept(...).thenRun(...)` chain. Assert business ordering only in the chained version; do not rely on sibling order from a lucky run.

## 35. Official References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): **Policies** section, non-Async dependent completion execution, default async facility, `thenApply/thenApplyAsync`, `thenCompose`, `complete`, `cancel`, `join`.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): semantics of dependent stages, function/consumer callbacks, synchronous/async variants, and exceptional completion.
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute` and memory consistency.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): thread pools, lifecycle, shutdown, and Future completion.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, cancellation, and memory consistency.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool and work-stealing context.
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): dependent failure and cause.
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before, thread safety, and memory visibility.

**Conclusion:** a `CompletableFuture` callback without the `Async` suffix **is not dispatched to a fixed executor by default**. It may be executed by the thread completing the source or a caller participating in completion; if the source is already completed, it may run immediately on the thread registering the callback. When a callback is heavy, blocking, or has thread affinity requirements, use `Async(..., Executor)` with clear ownership, capacity, and deadlines. Outcomes and exceptions belong to each stage separately, so wait on the dependent stage when confirming callback completion and pass context intentionally rather than inferring it from thread identity.