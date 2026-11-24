# Async Variants and Explicit Executor Selection in CompletableFuture

**CompletableFuture** lets you chain multiple asynchronous stages into a pipeline: generating data, transforming results, calling additional services, combining branches, handling errors, and returning a final result. What matters in **Spring Framework - concurrency** is not just writing a method ending in **Async**, but also answering: **which stage runs where, which executor receives the work, when does it run immediately on the current thread, and how does that choice affect application resources?**

This lesson belongs to the **CompletableFuture Composition** group, focusing on **Async variants and explicit executor selection**. The core focus is comparing non-Async and Async variants, specifying an Executor per step, understanding JDK defaults, coordinating with Spring **@Async** and **ThreadPoolTaskExecutor**, avoiding pool exhaustion, handling overload failures, and writing Java 17 tests with deterministic output.

First principles:

- **thenApply** without Async: the dependent task may run on the thread completing the previous stage or in an appropriate completion context; there is no guarantee of a dedicated worker.
- **thenApplyAsync(fn)**: registers a step executed asynchronously by `CompletableFuture`'s **default asynchronous execution facility**; for standard `CompletableFuture`, this is usually **ForkJoinPool.commonPool()**, not a Spring executor by default.
- **thenApplyAsync(fn, executor)**: requests the **explicitly supplied** executor to run that callback step.
- **thenComposeAsync(fn, executor)**: the executor is used to run the **fn function that produces the next CompletionStage**, and does not automatically impose that executor on all stages inside the stage `fn` returns.
- Spring's **@Async("beanName")** and JDK's **CompletableFuture.*Async(..., executor)** are **two separate executor-selection mechanisms**. Configuring one does not automatically set the default executor for every step in the other.

## 1. Three Common Execution Choices in CompletableFuture

Imagine a workflow: load data from an external system, normalize the result, and then compute a score.

~~~text
Request thread
    |
    +-- supplyAsync(load, ioExecutor)
                  |
                  | data completed
                  v
         thenApplyAsync(transform, cpuExecutor)
                  |
                  v
         thenComposeAsync(nextStageFactory, cpuExecutor)
                  |
                  +-- nextStageFactory returns a CompletionStage
                      whose operation runs on another executor if specified
                  |
                  v
              final result
~~~

For the same transformation task, the three calls below have different meanings:

~~~java
CompletableFuture<Integer> source = /* a valid future */;

CompletableFuture<Integer> a =
        source.thenApply(n -> n * 2);

CompletableFuture<Integer> b =
        source.thenApplyAsync(n -> n * 2);

CompletableFuture<Integer> c =
        source.thenApplyAsync(n -> n * 2, cpuExecutor);
~~~

This is an **illustrative snippet inside a method that has `source` and `cpuExecutor`**, not a standalone Java program.

| Form | Where the callback executes | What must not be assumed |
| --- | --- | --- |
| **thenApply(fn)** | Per `CompletionStage` non-async mechanics: may be the thread completing the previous stage, or a caller participating in completion/registration when applicable | Not guaranteed to run in a new executor |
| **thenApplyAsync(fn)** | `CompletableFuture`'s default async facility; usually `commonPool` for standard `CompletableFuture` | Not guaranteed to run in Spring's `ThreadPoolTaskExecutor` |
| **thenApplyAsync(fn, executor)** | The passed executor receives the execution of `fn` | Not guaranteed to be a new thread distinct from caller under every custom `Executor` |

That last point is especially important: **Async** means the callback is **handed to the chosen asynchronous execution facility**. If you intentionally pass a **direct-running Executor** (`Runnable::run`) or use a rejection policy like **CallerRunsPolicy** when the pool is full, the callback can still execute directly on the submitting thread. Thus, **Async is not a promise that the callback always runs on a different OS thread** under every executor configuration.

## 2. Non-Async: Optimizing Small Steps While Knowing Where They Can Run

Variants without the Async suffix—such as **thenApply**, **thenAccept**, **thenRun**, **thenCompose**, **thenCombine**, **whenComplete**, and **handle**—do not request a separate executor for the callback.

Under `CompletableFuture`'s contract, dependent completion actions in non-async variants **may be executed by the thread completing the current future or by another caller invoking a completion method**.

Two common scenarios:

**Case A — stage already completed when registering the callback:**

~~~java
Thread caller = Thread.currentThread();

boolean onCaller = CompletableFuture.completedFuture(10)
        .thenApply(n -> Thread.currentThread() == caller)
        .join();

System.out.println(onCaller);
~~~

This is a **Java 17 method-body snippet**. With an already-completed future and standard `thenApply` in this example, the callback runs directly on the registering thread, printing **true**. Do not extrapolate from this observation that **all** `thenApply` callbacks run on the caller.

**Case B — stage not yet completed:** the callback is registered first, and later a worker finishes the source stage. The non-async callback can commonly run on the thread that completed the source. If that callback performs long blocking I/O or heavy CPU work, it can extend how long a worker from the previous task remains occupied.

Selection rules:

- **Very lightweight, non-blocking, lock-free** transformations such as mapping DTO fields or simple checks: non-async is usually reasonable.
- **CPU-heavy tasks, blocking I/O, workload isolation, or resource partitioning**: consider Async with an explicit `Executor`.
- If the result must run on a thread with special affinity (UI/event loop), **do not rely on non-async `thenApply`** to guarantee affinity; use your framework's proper dispatch mechanism.

**Non-async does not mean the entire pipeline is synchronous.** If the source stage finishes after one minute, `thenApply` still triggers only after the source finishes. Here non-async describes **how the dependent callback is executed**, not that every source runs on the caller.

## 3. Async Is Not Just Blindly Using ForkJoinPool.commonPool

When calling **CompletableFuture.supplyAsync(supplier)** or **thenApplyAsync(fn)** **without passing an Executor**, standard `CompletableFuture` uses the default async facility, typically **ForkJoinPool.commonPool()**. Per Java 17 Javadoc, if `commonPool` does not support a parallelism level of at least two, the default may use a **new thread per task** instead. A `CompletableFuture` subclass can also customize **defaultExecutor()** for instance methods.

Therefore, saying "every default Async method always runs on `commonPool`" is too absolute. For typical application code, treat **`commonPool` as the usual default**, and verify configuration/runtime behavior whenever a difference matters operationally.

**Why pay attention to commonPool?**

- It is a **process-wide shared resource** of the JVM, not a dedicated pool for one Spring service.
- A pipeline running lots of blocking I/O on `commonPool` can contend with other tasks across the same JVM.
- `commonPool`'s size and policy do not automatically match your application's **CPU-bound**, **I/O-bound**, connection pool, or latency targets.
- Having a Spring method annotated with **@Async("myExecutor")** does not automatically make **thenApplyAsync() without an executor argument** inside it run on `myExecutor`.
- Using Async without an executor makes workload classification and tracing harder when multiple subsystems share `commonPool`.

**There is no need to ban commonPool absolutely.** It can be useful for small, intentional CPU-bound work. However, for backends with clear operational requirements, **choosing an explicit Executor** at controlled stages generally makes reasoning and measurement easier.

## 4. API Groups: Async Variants to Recognize

### 4.1 Creating Root Tasks

| Method | Purpose | Variant with Executor |
| --- | --- | --- |
| **CompletableFuture.supplyAsync(supplier)** | Executes `Supplier` to produce a result value | **supplyAsync(supplier, executor)** |
| **CompletableFuture.runAsync(runnable)** | Runs `Runnable`; future returns `Void` | **runAsync(runnable, executor)** |
| **future.completeAsync(supplier)** | Attempts to complete the future asynchronously with `Supplier`'s result | **completeAsync(supplier, executor)** |

**runAsync** is the choice when a task **returns no value**, though it still returns `CompletableFuture<Void>` to track completion and errors. **supplyAsync** fits tasks that return a value. **completeAsync** operates on an already-existing future where completion may race; it is not a mechanical substitute for `supplyAsync`.

### 4.2 Single Source Stage, Handling Successful Values

| Non-async | Default Async | Async with Executor | Meaning |
| --- | --- | --- | --- |
| **thenApply(fn)** | **thenApplyAsync(fn)** | **thenApplyAsync(fn, ex)** | `T -> U`, returns a value |
| **thenAccept(consumer)** | **thenAcceptAsync(consumer)** | **thenAcceptAsync(consumer, ex)** | Uses `T`, produces no new value |
| **thenRun(runnable)** | **thenRunAsync(runnable)** | **thenRunAsync(runnable, ex)** | Runs after success, does not receive `T` |
| **thenCompose(fn)** | **thenComposeAsync(fn)** | **thenComposeAsync(fn, ex)** | `T -> CompletionStage<U>`, flattens result |

**thenApply** transforms `T` into `U`. If `fn` **returns `CompletableFuture<U>`**, the result becomes **`CompletableFuture<CompletableFuture<U>>`**; in that case you normally need **thenCompose** to avoid nested futures.

### 4.3 Combining Two Stages

| Non-async | Async with Executor | When triggered |
| --- | --- | --- |
| **thenCombine(other, fn)** | **thenCombineAsync(other, fn, ex)** | Both stages complete normally; takes both values to compute `U` |
| **thenAcceptBoth(other, consumer)** | **thenAcceptBothAsync(other, consumer, ex)** | Both complete normally; consumes both results |
| **runAfterBoth(other, action)** | **runAfterBothAsync(other, action, ex)** | Both complete normally; runs without needing values |
| **applyToEither(other, fn)** | **applyToEitherAsync(other, fn, ex)** | When one stage completes normally meeting the condition |
| **acceptEither(other, consumer)** | **acceptEitherAsync(other, consumer, ex)** | Consumes successful result from one stage |
| **runAfterEither(other, action)** | **runAfterEitherAsync(other, action, ex)** | Runs after one stage succeeds per contract |

These APIs also have **Async variants without an Executor**; the table shows the three-argument form for two-source combinators to emphasize executor selection.

When two branches have scheduler-dependent completion order, **do not assume one branch always wins**. For **Either** methods, check normal/exceptional completion semantics in the Javadoc rather than treating them as an automatic "fastest successful result" under all failure cases.

### 4.4 Result and Error Handling

| Non-async | Async with Executor | Use case |
| --- | --- | --- |
| **whenComplete(action)** | **whenCompleteAsync(action, ex)** | Observes both success/error; normally preserves original outcome |
| **handle(fn)** | **handleAsync(fn, ex)** | Can turn either success or error into a new result `U` |
| **exceptionally(fn)** | **exceptionallyAsync(fn, ex)** | Recovers from an exception with a value `T` |
| **exceptionallyCompose(fn)** | **exceptionallyComposeAsync(fn, ex)** | Recovers with another `CompletionStage<T>` |

The **exceptionallyAsync** and **exceptionallyComposeAsync** variants are available in **Java 17**. Do not confuse them with **handleAsync**: `handle` receives both value and error, whereas `exceptionally` runs only when the preceding stage completes exceptionally.

**Note:** `whenComplete` is not a default recovery mechanism; if the source stage failed, `whenComplete` normally preserves the failed state after the observer callback runs, aside from special rules when the callback itself throws. When recovery is needed, choose `handle` or `exceptionally` as appropriate.

## 5. At What Level Is the Executor Chosen in a Pipeline?

Inspect this chain:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(this::load, ioExecutor)
            .thenApplyAsync(this::normalize, cpuExecutor)
            .thenComposeAsync(this::enrichAsync, cpuExecutor)
            .thenApply(this::format);
~~~

This is an **illustrative snippet in a class with `load`/`normalize`/`enrichAsync`/`format`, `ioExecutor`, and `cpuExecutor`**; it is not a standalone compilable program.

Assignment order:

1. **supplyAsync(..., ioExecutor)**: task **load** runs on `ioExecutor`.
2. **thenApplyAsync(..., cpuExecutor)**: callback **normalize** runs on `cpuExecutor`.
3. **thenComposeAsync(..., cpuExecutor)**: callback **enrichAsync** is dispatched via `cpuExecutor`. If `enrichAsync` itself returns a future created with **supplyAsync(..., networkExecutor)**, that future's work runs on **networkExecutor**.
4. **thenApply(this::format)**: no separate executor chosen. Callback `format` may run on the thread completing the previous stage, or another caller per non-async semantics.

There is no "permanent executor inheritance" from the first stage. Using **supplyAsync(..., ioExecutor)** does not mean subsequent **thenApplyAsync(...)** calls default to `ioExecutor`. To guarantee which pool each important step runs on, **pass the Executor on that specific step's call**.

### Red Flag During Code Review

~~~java
CompletableFuture.supplyAsync(() -> fetch(), ioExecutor)
        .thenApplyAsync(data -> heavyCompute(data));
~~~

**heavyCompute** does not automatically run on `ioExecutor`; an Async callback without an Executor argument uses the default facility. For an isolated CPU workload, fix it to:

~~~java
CompletableFuture.supplyAsync(() -> fetch(), ioExecutor)
        .thenApplyAsync(data -> heavyCompute(data), cpuExecutor);
~~~

Both snippets are **illustrative**, assuming `fetch`/`heavyCompute` and the executors are declared. The fix is not "adding Async," but **putting the right executor at the right boundary**.

## 6. Standalone Java 17 Example: Each Variant Using the Right Executor

This example **does not depend on Spring**. It creates two clearly named single-thread executors and sequentially exercises **supplyAsync**, **thenApplyAsync**, **thenComposeAsync**, and a nested future branch. It does not claim Async always creates new threads; here **we explicitly choose two `ExecutorService` instances** with dedicated workers.

Create **`AsyncVariantsDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncVariantsDemo {
    private static ExecutorService namedSingleThread(String name) {
        return Executors.newSingleThreadExecutor(
                task -> new Thread(task, name));
    }

    public static void main(String[] args) throws Exception {
        Thread caller = Thread.currentThread();

        ExecutorService io = namedSingleThread("io-worker");
        ExecutorService cpu = namedSingleThread("cpu-worker");

        AtomicReference<String> sourceThread = new AtomicReference<>();
        AtomicReference<String> mapThread = new AtomicReference<>();
        AtomicReference<String> composeThread = new AtomicReference<>();
        AtomicReference<String> nestedThread = new AtomicReference<>();
        AtomicReference<String> finalThread = new AtomicReference<>();

        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.supplyAsync(() -> {
                        sourceThread.set(Thread.currentThread().getName());
                        return 10;
                    }, io);

            CompletableFuture<String> pipeline = source
                    .thenApplyAsync(value -> {
                        mapThread.set(Thread.currentThread().getName());
                        return value * 2;
                    }, cpu)
                    .thenComposeAsync(value -> {
                        composeThread.set(Thread.currentThread().getName());
                        return CompletableFuture.supplyAsync(() -> {
                            nestedThread.set(
                                    Thread.currentThread().getName());
                            return value + 5;
                        }, io);
                    }, cpu)
                    .thenApplyAsync(value -> {
                        finalThread.set(Thread.currentThread().getName());
                        return "value=" + value;
                    }, cpu);

            String result = pipeline.get(5, TimeUnit.SECONDS);

            boolean nonAsyncOnCaller =
                    CompletableFuture.completedFuture(7)
                            .thenApply(x -> Thread.currentThread() == caller)
                            .join();

            System.out.println("Non-async on caller: "
                    + nonAsyncOnCaller);
            System.out.println("supplyAsync: " + sourceThread.get());
            System.out.println("thenApplyAsync: " + mapThread.get());
            System.out.println("thenComposeAsync: " + composeThread.get());
            System.out.println("nested supplyAsync: " + nestedThread.get());
            System.out.println("final thenApplyAsync: " + finalThread.get());
            System.out.println("result: " + result);
        } finally {
            io.shutdown();
            cpu.shutdown();
            if (!io.awaitTermination(5, TimeUnit.SECONDS)) {
                io.shutdownNow();
            }
            if (!cpu.awaitTermination(5, TimeUnit.SECONDS)) {
                cpu.shutdownNow();
            }
        }
    }
}
~~~

Compile and run commands (JDK 17+):

~~~bash
javac -encoding UTF-8 AsyncVariantsDemo.java
java AsyncVariantsDemo
~~~

**Program stdout**, assuming both executors work normally and tasks finish within the test timeout:

~~~text
Non-async on caller: true
supplyAsync: io-worker
thenApplyAsync: cpu-worker
thenComposeAsync: cpu-worker
nested supplyAsync: io-worker
final thenApplyAsync: cpu-worker
result: value=25
~~~

Analyzing each result:

- **sourceThread** is `io-worker` because the initial supplier was assigned to **io**.
- **mapThread** is `cpu-worker` because **thenApplyAsync** specified **cpu**.
- **composeThread** is `cpu-worker` because the **CompletionStage-creating function** itself was dispatched to **cpu**.
- **nestedThread** goes back to `io-worker` because **the function returns a new `CompletableFuture`** via **supplyAsync(..., io)**. `thenComposeAsync`'s executor **does not govern the work inside the nested future**.
- **finalThread** is `cpu-worker` because the final `thenApplyAsync` specified `cpu`.
- **result** equals `value=25` because `10 * 2 + 5`.
- The **completedFuture(7).thenApply(...)** check runs the callback immediately upon registration on the example's caller thread, producing **true**. That is not a guarantee for incomplete futures.

The program prints only after calling **get(timeout)** on the final result, so log output does not depend on worker execution order. Worker names come from explicitly configured **ThreadFactory** instances. The `AtomicReference` values are read after the futures complete, ensuring visibility of the values written in their respective stages.

**Measurement limitation:** the example proves **which stage is routed to which executor in a specific configuration**, not throughput benchmarks. Single-thread executors here make explanation and verification easy; do not copy a 1-worker limit straight to production without evaluating workload.

## 7. How Does thenApplyAsync Differ from thenComposeAsync?

Consider a service method returning a future:

~~~java
CompletableFuture<User> loadUserAsync(String id) {
    return CompletableFuture.supplyAsync(
            () -> queryUser(id), ioExecutor);
}
~~~

This is an **illustrative method snippet** with `User`, `queryUser`, and `ioExecutor` defined in the application. When loading a user after obtaining an ID:

~~~java
CompletableFuture<String> idFuture = /* source stage */;

// Creates a future nested inside a future:
CompletableFuture<CompletableFuture<User>> nested =
        idFuture.thenApplyAsync(
                id -> loadUserAsync(id),
                cpuExecutor);

// Flattens to get a single User future:
CompletableFuture<User> flat =
        idFuture.thenComposeAsync(
                id -> loadUserAsync(id),
                cpuExecutor);
~~~

**thenApplyAsync** accepts a function **`T -> U`**. If `U` is `CompletableFuture<User>`, the result is **`CompletableFuture<CompletableFuture<User>>`**.

**thenComposeAsync** accepts a function **`T -> CompletionStage<U>`**, and creates a dependent stage reflecting the **eventual result** of the stage returned by the function. That gives us **`CompletableFuture<User>`** instead of nested futures.

In this code **cpuExecutor runs the function calling `loadUserAsync`**. Yet `loadUserAsync` internally submits work via **supplyAsync(..., ioExecutor)**, so `queryUser` executes on **ioExecutor**. This is where many people confuse **the executor of the future-creating callback** with **the executor of the work represented by that future**.

An alternative can make sense if the future-creating function performs only trivial work:

~~~java
CompletableFuture<User> flat =
        idFuture.thenCompose(id -> loadUserAsync(id));
~~~

Here creating/registering the future is not separately dispatched, while `queryUser` **can still run on `ioExecutor`** because `loadUserAsync` uses `supplyAsync` with `ioExecutor`. If the `thenCompose` function only initiates a future without blocking, this avoids an unnecessary thread hop.

**Summary:** choose **thenApply(Async)** when transforming a value, and **thenCompose(Async)** when the function returns a **CompletionStage**. Deciding **Async vs. non-async** for the callback function is orthogonal to choosing **Apply vs. Compose**.

## 8. thenCombineAsync: Combining Two Independent Tasks

Suppose a total price must be computed from two independent sources:

~~~java
CompletableFuture<Integer> baseFuture =
        CompletableFuture.supplyAsync(
                () -> loadBasePrice(), ioExecutor);

CompletableFuture<Integer> feeFuture =
        CompletableFuture.supplyAsync(
                () -> loadFee(), ioExecutor);

CompletableFuture<Integer> totalFuture =
        baseFuture.thenCombineAsync(
                feeFuture,
                (base, fee) -> base + fee,
                cpuExecutor);
~~~

This is an **illustrative snippet in an application** where `loadBasePrice`/`loadFee` and the executors are defined. Both source futures can progress concurrently, subject to executor capacity and downstream resources. The addition function runs only after both stages complete normally, on **cpuExecutor**.

If you only add two numbers, the callback is very lightweight; non-Async **thenCombine** can suffice. Specifying an executor becomes valuable when the combining work is truly **CPU-intensive**, needs **thread affinity**, or requires workload isolation.

### allOf and anyOf Are Not Async Overloads with an Executor

**CompletableFuture.allOf(f1, f2, ...)** creates an aggregate future that completes when all input futures complete; it **does not return a list of values**. You still read each result from the original futures once completion is guaranteed.

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(baseFuture, feeFuture);

CompletableFuture<Integer> total = all.thenApplyAsync(
        ignored -> baseFuture.join() + feeFuture.join(),
        cpuExecutor);
~~~

This is an **illustrative snippet** with two futures returning `Integer`. When `all` completes **normally**, all member futures have already completed normally, so `join` inside the callback does not wait further for them to run. If an input future fails, `all` can complete exceptionally and `thenApplyAsync` does not run; the caller must handle the error branch separately.

**allOf** itself **takes no Executor parameter**. To run post-processing on a specific pool, chain **thenApplyAsync/thenRunAsync/... with an Executor** onto the combined future. **anyOf** returns a future with value type **Object** and completes with whichever member finishes first; it is likewise not syntax for configuring an executor across all input branches.

Do not think **allOf** opens a pool or re-runs tasks itself. It only **combines completions** of existing futures.

## 9. Async Variants of Terminal Steps and Error Handling

### thenAcceptAsync and thenRunAsync

~~~java
CompletableFuture<Order> orderFuture = /* valid future */;

CompletableFuture<Void> audit =
        orderFuture.thenAcceptAsync(
                order -> auditOrder(order),
                auditExecutor);

CompletableFuture<Void> cleanup =
        audit.thenRunAsync(
                () -> markAuditComplete(),
                auditExecutor);
~~~

**thenAcceptAsync** receives `Order` and returns a `Void` stage. **thenRunAsync** receives no `Order`/input result, running only after the upstream succeeds. Both steps are requested to run via **auditExecutor**, subject to the executor accepting the work.

**Note:** a side-effecting action like auditing must have clear idempotency and error rules. If auditing is mandatory, do not treat an in-memory registered callback as confirmation that the work is durably persisted.

### whenCompleteAsync and handleAsync

~~~java
CompletableFuture<String> observed =
        sourceFuture.whenCompleteAsync(
                (value, error) -> logOutcome(value, error),
                logExecutor);

CompletableFuture<String> recovered =
        sourceFuture.handleAsync(
                (value, error) -> error == null
                        ? value
                        : "fallback",
                recoveryExecutor);
~~~

This is an **illustrative snippet** with existing `sourceFuture`, `logOutcome`, and executors. **whenCompleteAsync** fits observing/logging and normally preserves the original result or error; **handleAsync** returns a new value so it can turn an exceptional completion into a normal result if logic permits.

### exceptionallyAsync and exceptionallyComposeAsync

Java 17 provides these APIs:

~~~java
CompletableFuture<String> recoveredValue =
        sourceFuture.exceptionallyAsync(
                error -> "fallback",
                recoveryExecutor);

CompletableFuture<String> recoveredStage =
        sourceFuture.exceptionallyComposeAsync(
                error -> fetchFromBackupAsync(),
                recoveryExecutor);
~~~

**exceptionallyAsync** produces a recovery value upon error. **exceptionallyComposeAsync** calls a function producing another **`CompletionStage<String>`** and merges that stage's result. In the second example, **recoveryExecutor** runs the function that creates the backup stage; the future returned by **fetchFromBackupAsync()** still obeys its own executor/mechanism.

Do not use a blanket fallback to hide all business errors. For instance, authorization failures or invalid requests normally should not be turned into fake valid data. Classify the exception/cause before deciding to recover or retry.

**Distinguish scheduler errors from task errors:** a task may be **rejected by the executor before running**, or run and throw an exception. How errors surface with `CompletableFuture` depends on the API and **when** rejection occurs; handle both submission/registration paths and exceptional future completion rather than assuming every failure can be caught with `exceptionally`.

## 10. Which Executor Should You Choose? Distinguishing CPU-Bound, I/O-Bound, and Downstream

An application can choose multiple executors instead of dumping every stage into one pool:

| Workload | Examples | Executor selection guideline |
| --- | --- | --- |
| CPU-bound | large scoring, heavy data conversion, compression | Bounded worker pool sized to CPU capacity; avoid severe oversubscription |
| Blocking I/O | synchronous HTTP client, blocking DB driver, file access | Dedicated workers with concurrency aligned to connection pools and timeouts |
| Lightweight log/metrics | counters, non-long-blocking logging | Usually no need to hop executors per operation; pick an appropriate telemetry system |
| Mandatory durable tasks | payment jobs, critical emails | Durable queue/job store or outbox; do not trust in-memory Futures alone |
| Future coordination logic | chaining stages, combining results, picking fallbacks | Non-async if truly trivial; Async with executor if isolation/affinity is needed |

There is no universal rule that "an I/O pool must always have N threads." If the database only permits 10 concurrent connections, letting 1,000 blocking DB tasks run on 1,000 platform threads increases waiting and memory usage without increasing throughput. **A CPU pool likewise does not gain extra compute capacity by endlessly increasing worker counts.**

### Spring's ThreadPoolTaskExecutor

**ThreadPoolTaskExecutor** can be used as a standard **Executor** passed to **CompletableFuture.*Async(..., executor)**. Its settings include:

- **corePoolSize**: core worker count.
- **maxPoolSize**: maximum worker count.
- **queueCapacity**: queued task capacity; **0** selects `SynchronousQueue` / direct handoff.
- **threadNamePrefix**: worker name prefix for logging/debugging.
- **RejectedExecutionHandler**: handles overload when no more tasks can be accepted.
- **shutdown/lifecycle** options suited to application requirements.

An overly large queue can accumulate backlog and prevent `maxPoolSize` from ever scaling up. A queue capacity of 0 lets the pool expand quickly up to max, yet also triggers rejections sooner. Tune parameters to load, SLAs, deadlines, and downstream resources; do not treat numbers in lesson examples as default production settings.

## 11. Spring @Async and CompletableFuture: Two Distinct Dispatch Layers

Spring **@Async** lets **Spring AOP/interceptors** offload method execution onto an executor. A method annotated with **@Async("ioExecutor")** uses the specified bean/qualifier executor to run the **method body** through Spring's proxy mechanism. That **does not change the default of `CompletableFuture.thenApplyAsync(...)`** in downstream stages.

Diagram:

~~~text
Caller thread
   |
   +-- Spring proxy: @Async("ioExecutor")
   |          |
   |          +-- ioExecutor runs body of service.load()
   |                       |
   |                       +-- returns CompletableFuture result
   |
   +-- receives CompletableFuture from proxy
              |
              +-- thenApplyAsync(fn, cpuExecutor)
              |          |
              |          +-- CPU executor runs fn
              |
              +-- thenApplyAsync(fn)  [no executor passed]
                         |
                         +-- CF's default async facility
                             (usually commonPool, not ioExecutor)
~~~

With standard **@Async**, a method requires a supported return type such as **void**, **Future**, or **CompletableFuture** per Spring's contract. Inside a method body already dispatched by Spring to `ioExecutor`, once computation finishes you can return **CompletableFuture.completedFuture(value)**. The caller receives the future provided by the Spring proxy to track asynchronous execution.

**There is no need to call `supplyAsync` again inside an `@Async` method.** Writing `@Async("ioExecutor")` and then calling **supplyAsync(..., cpuExecutor)** inside the body without a specific reason adds another scheduling layer, complicating context propagation, timing, error observation, and shutdown.

### Configuring Two Spring Executors and Explicitly Choosing Each Stage

The Spring application example below uses:

- Bean **ioExecutor** for the body of **@Async**.
- Bean **cpuExecutor** as the argument to **thenApplyAsync**.
- Both pools have a single worker solely to verify the execution path, **not a size to use in production**.

Maven directory layout:

~~~text
spring-explicit-executor/
├── pom.xml
└── src/main/java/example/SpringAsyncSelectionDemo.java
~~~

**pom.xml** (Spring Framework 6.2.12 and Java 17):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-explicit-executor</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <configuration>
                    <mainClass>example.SpringAsyncSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/SpringAsyncSelectionDemo.java**:

~~~java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SpringAsyncSelectionDemo {
    private static final AtomicReference<String> ioThread =
            new AtomicReference<>();
    private static final AtomicReference<String> cpuThread =
            new AtomicReference<>();

    @Configuration
    @EnableAsync
    public static class Config {
        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("io-");
            return pool;
        }

        @Bean("cpuExecutor")
        public ThreadPoolTaskExecutor cpuExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("cpu-");
            return pool;
        }

        @Bean
        public ReportWorker reportWorker() {
            return new ReportWorker();
        }

        @Bean
        public ReportPipeline reportPipeline(
                ReportWorker worker,
                @Qualifier("cpuExecutor") Executor cpuExecutor) {
            return new ReportPipeline(worker, cpuExecutor);
        }
    }

    public static class ReportWorker {
        @Async("ioExecutor")
        public CompletableFuture<Integer> load(int value) {
            ioThread.set(Thread.currentThread().getName());
            return CompletableFuture.completedFuture(value + 1);
        }
    }

    public static class ReportPipeline {
        private final ReportWorker worker;
        private final Executor cpuExecutor;

        public ReportPipeline(ReportWorker worker, Executor cpuExecutor) {
            this.worker = worker;
            this.cpuExecutor = cpuExecutor;
        }

        public CompletableFuture<Integer> run(int value) {
            return worker.load(value)
                    .thenApplyAsync(loaded -> {
                        cpuThread.set(Thread.currentThread().getName());
                        return loaded * 2;
                    }, cpuExecutor);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            int result = context.getBean(ReportPipeline.class)
                    .run(10)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("ioExecutor correct: "
                    + ioThread.get().startsWith("io-"));
            System.out.println("cpuExecutor correct: "
                    + cpuThread.get().startsWith("cpu-"));
            System.out.println("Result: " + result);
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java
~~~

**Program stdout** (excluding Maven/Spring logs, environment-dependent):

~~~text
ioExecutor correct: true
cpuExecutor correct: true
Result: 22
~~~

Explanation:

1. **@EnableAsync** enables detection of **@Async**. `ReportWorker` is a Spring-managed bean, `load` is **public** and non-final, and is invoked by **ReportPipeline** (a different bean) via Spring-injected dependency, allowing the async proxy to work.
2. **@Async("ioExecutor")** tells Spring to dispatch **the body of `load`** onto the `ioExecutor` pool. The body records the worker name, computes `10 + 1 = 11`, and returns **completedFuture(11)**; the interceptor supplies the appropriate future to the caller.
3. `ReportPipeline` registers **thenApplyAsync(..., cpuExecutor)**, so multiplying `11 * 2` runs on the `cpuExecutor` pool.
4. **get(timeout)** is called in `main` to wait for completion before printing; thus output does not depend on worker execution order.
5. Both thread names come from **setThreadNamePrefix**, and the code checks prefixes instead of guessing worker sequence numbers.
6. The `ThreadPoolTaskExecutor` beans are managed and initialized by Spring in the context; when the context closes, executor lifecycles are coordinated by the container. In plain Java programs you must shut down `ExecutorService` explicitly.

This is a **self-contained technical example in a Maven project with appropriate dependencies**. It illustrates two independent executor-selection layers, not a complete production framework for security, timeouts, metrics, and error handling.

## 12. Selecting Executors via @Async, Qualifiers, and AsyncConfigurer

Spring offers several levels of selection:

**A. Specifying directly on a method:**

~~~java
@Async("ioExecutor")
public CompletableFuture<Data> read() {
    return CompletableFuture.completedFuture(loadData());
}
~~~

This is an **illustrative method snippet** inside a Spring bean. The string **ioExecutor** must match a bean name or qualifier that Spring can resolve to an `Executor`/`TaskExecutor`.

**B. Specifying on a class:**

~~~java
@Async("ioExecutor")
public class ExternalApiWorker {
    public CompletableFuture<String> call() {
        return CompletableFuture.completedFuture("ok");
    }
}
~~~

This is an **illustrative class snippet** (still needs bean registration), not a full application. Method-level **@Async("otherExecutor")** can **override the class-level qualifier** per Spring's rules.

**C. Default configuration of async support:**

You can implement **AsyncConfigurer** in Spring to provide a default executor for **@Async methods without a qualifier**, or to configure exception handling for `async void` methods. Default bean naming conventions in the framework can also affect selection if not specified explicitly. Avoid mixing these mechanisms and guessing the actual executor solely from the annotation string.

**D. Specifying on individual CompletableFuture callbacks:**

~~~java
return worker.load()
        .thenApplyAsync(this::transform, cpuExecutor)
        .thenComposeAsync(this::saveAsync, ioExecutor);
~~~

This is an **illustrative method snippet with dependencies**; the `Executor` argument on each Async callback determines where that callback is dispatched. The **@Async("ioExecutor")** qualifier on `worker.load` **does not replace** those two arguments.

**Organizational takeaway:** choose the Spring method's executor with **@Async("...")**, choose each `CompletionStage` callback's executor with the **Async variant taking an `Executor`**, and verify bean names/qualifiers with integration tests.

## 13. Explicit Executors Do Not Automatically Propagate ThreadLocal, MDC, and Security Context

Many pieces of data in Spring are bound to the thread handling a request, such as:

- **MDC** used for logging.
- **SecurityContext** depending on the context-holder strategy.
- **RequestContextHolder** and request attributes.
- **Transaction/persistence contexts** bound to the thread's transaction.
- Custom application `ThreadLocal` values.

When moving from the **request thread** to **ioExecutor** and then on to **cpuExecutor**, those contexts **do not automatically follow every step**. Using named executors controls resources, but does not automatically enable context propagation.

Common mistake example:

~~~java
CompletableFuture<String> future = CompletableFuture
        .supplyAsync(() -> callRemote(), ioExecutor)
        .thenApplyAsync(value -> {
            // Do not assume MDC, Principal, or transaction
            // from the HTTP request thread is present here.
            return process(value);
        }, cpuExecutor);
~~~

This is an **illustrative snippet**, not standalone runnable code.

Proper design:

1. **Business data**: build an immutable snapshot of required inputs before submitting tasks.
2. **Logging/tracing**: use official context propagation mechanisms from the Spring/Micrometer stack or a properly configured **TaskDecorator**; clean up/restore context after callbacks since workers are reused.
3. **Security**: consider Spring Security delegating/wrapping executors or re-authenticate/re-authorize at critical execution points. Do not blindly share entire principals/tokens.
4. **Transactions**: a request thread's transaction does not extend across Async stages. Open transactions appropriate to worker operations, typically through properly proxied transactional service beans.
5. **Multiple executor hops**: if a pipeline crosses multiple boundaries (`io -> cpu -> io`), address propagation and cleanup at **each boundary**, not only the first stage.

**Do not use mutable fields on a singleton bean to simulate cross-thread request context.** That allows concurrent requests to overwrite each other's data.

## 14. Overload and Rejection Across Async Stages

When calling Async with an explicit `Executor`, a dependent stage may **fail to be scheduled** if the executor is shut down or saturated. For example, **ThreadPoolTaskExecutor** with a bounded queue and bounded workers can throw **TaskRejectedException** per Spring's contract; JDK **ThreadPoolExecutor** typically signals rejection with **RejectedExecutionException**.

Distinction:

| Issue | Where it occurs | How to handle |
| --- | --- | --- |
| Task not accepted | When submitting/scheduling a stage | Catch errors that may happen on the call path; observe exceptional completion when the API surfaces it via future; define retry/overload policy |
| Error inside supplier/function | After the stage is accepted and runs | Corresponding future completes exceptionally; use `handle`/`exceptionally`/`whenComplete` |
| Task waits too long in queue | After acceptance, before execution | Deadlines/timeouts, queue-wait metrics, bounded backlogs |
| Blocked by `join`/`get` | Thread calling `join`/`get` | Avoid blocking inside capacity-limited workers; use composition |
| Callback runs on caller | Direct Executor or `CallerRunsPolicy` | Never assume Async always keeps the caller unblocked |

**An easily overlooked detail:** if you call **thenApplyAsync(fn, executor)** when the source stage **is already complete**, the implementation may attempt to schedule the callback **immediately inside the registration call**. If the executor refuses it, the error may surface differently than when the source stage **completes later** and rejection occurs while the future triggers dependent actions. Do not claim all rejections always land inside a `Future` or always throw synchronously at the same line across all implementations. Write tests for your actual executor and API, handling both the submission boundary and exceptional completion.

**With @Async**, Spring proxy submission into the executor is itself a separate boundary; **TaskRejectedException** can be thrown to the caller **before a `CompletableFuture` is even returned**. If the task was accepted and the body throws, the future carries the exceptional completion.

### Rejection Policies Are Not a Way to "Eliminate Errors"

- **AbortPolicy**: rejects via exception, making saturation observable.
- **CallerRunsPolicy**: when not shut down, can execute the task on the submitting thread, causing Async functions to run on the caller under overload.
- **DiscardPolicy/DiscardOldestPolicy**: risks losing work or leaving a `Future` that never completes unless discarded task states are managed.

A backend must define explicitly whether tasks are allowed to be dropped. If they cannot be lost, an in-memory executor **does not replace a durable job queue/outbox**; you need durable acceptance state plus appropriate retry/idempotency.

## 15. Avoiding Deadlock and Starvation When Sharing One Pool

A common bug: submitting a task to an **executor with only one worker**, and then **inside that task** submitting a subtask to the **same executor** and calling **`join()`** to wait for it:

~~~java
ExecutorService oneWorker = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> result =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> nested =
                    CompletableFuture.supplyAsync(() -> 42, oneWorker);
            return nested.join(); // Deadlock risk!
        }, oneWorker);
~~~

This is a **dangerous illustrative snippet**, not a program to run: while the single worker waits on `nested.join()`, the nested task sits in the queue with no second worker available to execute it. Do not run this example without external cancellation/timeout; it can hang.

Replace with **composition that does not block inside the worker**:

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.supplyAsync(() -> 10, oneWorker)
                .thenComposeAsync(
                        n -> CompletableFuture.supplyAsync(
                                () -> n + 32, oneWorker),
                        oneWorker);
~~~

This is an **illustrative snippet**. `thenComposeAsync` runs the function creating the new future on the executor, yet **does not call `join` on the inner future while holding the worker**; the worker is free to execute the nested task afterward. With one worker, both tasks can finish in turn without holding the worker hostage waiting on each other.

Still, **adding `thenCompose` does not make every system deadlock-proof**. You must still check locks, database connections, transactions, other task batches, queues, and exceptions. The key is **never blocking a worker on work that must acquire that same worker to make progress**.

### Which Layer Owns join/get?

- **get(timeout)** on a boundary coordination thread can be useful for waiting on a result with a deadline.
- **join()** inside a task running on a small pool increases saturation risk and negates async pipeline benefits.
- **thenCompose** turns "wait for a sub-stage" into **composition** without a worker actively blocking in `join`.
- If blocking is unavoidable because an external API is synchronous-only, allocate an appropriate pool and set clear timeouts instead of pretending it is non-blocking.

## 16. Timeouts, delayedExecutor, and Executor Selection

Java 17 provides these utilities:

- **orTimeout(timeout, unit)**: if the future is not complete by the deadline, completes it exceptionally with `TimeoutException` per contract.
- **completeOnTimeout(value, timeout, unit)**: completes the future with a fallback value if the deadline expires.
- **delayedExecutor(delay, unit, executor)**: creates an `Executor` adapter that delays when **the task is handed to the specified executor**.
- **CompletableFuture.copy()** and **minimalCompletionStage()**: help control how external callers access/complete stages in library API design; they do not choose callback threads.

**orTimeout** and **completeOnTimeout** take no separate `Executor` parameter to choose where business code runs; they affect completion state and do not mean the source task is interrupted/cancelled as soon as the timeout fires.

Example delaying a task:

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        200, TimeUnit.MILLISECONDS, ioExecutor);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "ok", delayed);
~~~

This is an **illustrative code snippet** with `ioExecutor`, `TimeUnit`, and `Executor` imported. The executor adapter waits and then passes the task to **ioExecutor**. It **does not imply downstream callbacks inherit `ioExecutor`**. If a subsequent transform should run on `cpuExecutor`, write **thenApplyAsync(fn, cpuExecutor)**.

A **business deadline** may include queue wait + execution + retries. A `CompletableFuture` timing out after 2 seconds does not automatically free a DB connection held by long blocking I/O; I/O resources need their own timeouts and cancellation.

## 17. Testing Executor Selection Deterministically

Do not prove Async behavior by sleeping with **Thread.sleep(50)** and inspecting log ordering. Design tests around what you actually need to verify:

**Testing pool separation:**

1. Create two `ExecutorService` instances with clearly named `ThreadFactory` threads, or record **Thread identity** in an `AtomicReference`.
2. Run **supplyAsync(..., ioExecutor)** and **thenApplyAsync(..., cpuExecutor)**.
3. Wait on the final future with **get(timeout)**.
4. Assert that the supplier/callback ran on the configured thread/executor.
5. Shut down pools in `finally` so tests do not leak workers.

**Testing non-async:**

1. Create an already-completed `completedFuture`.
2. Call `thenApply` and compare `Thread.currentThread()` inside the callback with the caller.
3. To test non-async execution when a stage completes later, coordinate with **CountDownLatch** instead of guessing execution order.
4. Do not turn one test observation into a rule that "all non-async callbacks always run on the caller."

**Testing @Async and proxies:**

1. Use **ApplicationContext**, never **`new ReportWorker()`** directly.
2. Enable **@EnableAsync**; invoke the method **through a Spring proxy from another bean**.
3. Avoid self-invocation `this.load()` or private/final methods incompatible with proxying.
4. Measure the thread running the method body separately from the thread running **thenApplyAsync(..., cpuExecutor)**.
5. Test executor saturation/shutdown, distinguishing **TaskRejectedException at submission** from exceptional future completion.

**Testing overload:**

- Configure a pool with bounded workers and a bounded queue.
- Hold running tasks with **CountDownLatch** and wait to confirm workers have started.
- Submit more tasks until saturated, then assert `Abort` or `CallerRuns` behavior per configuration.
- Always release latches and clean up in `finally`.
- Track rejected task counts, queue wait, active pool threads, and response latency impact.

## 18. Common Misconceptions

**"Async always creates a new thread."** False. `CompletableFuture.*Async` invokes an `Executor`; the executor may reuse workers, run directly, or use `CallerRuns` under overload.

**"thenApply and thenApplyAsync only differ by name; the result is the same so it doesn't matter."** False. They differ in thread selection and impact on latency, saturation, and context, even when the final value is identical.

**"supplyAsync(..., ioExecutor) forces every subsequent thenApplyAsync to use ioExecutor."** False. Every Async callback without an executor argument uses the default asynchronous facility; pass the executor at each boundary you want to control.

**"thenComposeAsync(..., cpuExecutor) runs every future returned by the function inside cpuExecutor."** False. `cpuExecutor` runs the callback creating the `CompletionStage`, while the returned future can use its own executor.

**"@Async("ioExecutor") makes CompletableFuture.thenApplyAsync() automatically use ioExecutor."** False. Spring `@Async` and JDK `CompletableFuture` have separate configuration mechanisms.

**"thenComposeAsync is always better than thenCompose."** False. If the future-creating function is tiny and non-blocking, non-async `thenCompose` avoids extra scheduling overhead. Evaluate actual needs.

**"thenApplyAsync makes heavy CPU work faster if you add unlimited threads."** False. CPUs still have core/cache limits and scheduling overhead; measure throughput and latency.

**"allOf automatically runs all input futures on a passed executor."** False. `allOf` only combines completions; input futures must be created and executed by their own mechanisms.

**"join/get inside a worker pool is just concise syntax and doesn't affect concurrency."** False. Blocking can cause starvation/deadlock, especially when subtasks need the same pool.

**"@Async always returns immediately and the caller never blocks."** Not necessarily. `CallerRunsPolicy` or submission failures can affect this; callers might also call `join`/`get` themselves afterward.

**"Pipeline exceptions and submission rejections can both be handled by a single exceptionally."** Do not assume that. Rejection can happen before a future is created/returned or while scheduling a dependent callback; inspect the actual API behavior.

**"orTimeout cancels the underlying task and frees all I/O resources."** False. It changes future completion semantics; interrupting/cancelling/timing out underlying operations requires separate design.

**"An explicit Executor means MDC, SecurityContext, and transactions automatically follow."** False. Context propagation is a separate problem requiring dedicated mechanisms and cleanup.

**"Returning a Future with 202 Accepted means the job is durably stored."** False. `CompletableFuture` is not a durable queue and does not survive JVM restarts.

## 19. Self-Check Questions

**Question 1.** You call **thenApplyAsync(fn)** without passing an `Executor` on a standard `CompletableFuture`. Is it guaranteed to use Spring's `ThreadPoolTaskExecutor`?

**Answer:** No. It uses `CompletableFuture`'s default asynchronous execution facility, typically `ForkJoinPool.commonPool()`.

**Question 2.** You call **thenApplyAsync(fn, cpuExecutor)** after **supplyAsync(supplier, ioExecutor)**. Must `supplier` and `fn` use the same executor?

**Answer:** No. `supplier` is dispatched to `ioExecutor`; `fn` is dispatched to `cpuExecutor`.

**Question 3.** A non-async **thenApply(fn)** follows an incomplete future. Is `fn` guaranteed to run on the caller that built the chain?

**Answer:** No. `fn` may run on the thread completing the upstream or another caller involved in completion; there is no default thread affinity.

**Question 4.** The stage-creating function in **thenComposeAsync(fn, cpuExecutor)** returns **supplyAsync(..., ioExecutor)**. Where does the nested work run?

**Answer:** `fn` runs on `cpuExecutor`; the supplier of the returned future runs on `ioExecutor`.

**Question 5.** If `fn` returns `CompletableFuture<User>`, should you use **thenApply** or **thenCompose** to get **`CompletableFuture<User>`**?

**Answer:** `thenCompose`; `thenApply` would produce a nested future.

**Question 6.** Can **thenCombineAsync** aggregate two independent futures on a separate executor?

**Answer:** Yes. Pass `(other, function, executor)`, and the combining callback is scheduled on that executor once both sources complete normally.

**Question 7.** Does **allOf(f1, f2)** accept an executor parameter to move `f1`/`f2` onto a new pool?

**Answer:** No. `allOf` only creates an aggregate stage; to run post-processing on a specific pool, chain an Async callback with that `Executor`.

**Question 8.** Does **@Async("ioExecutor")** on a Spring service automatically govern **thenApplyAsync(fn)** on the caller side?

**Answer:** No. The caller must pass `ioExecutor` (or another executor) to `thenApplyAsync(fn, ioExecutor)` explicitly.

**Question 9.** If a single worker calls nested `Future.join()` while the nested task is waiting in the same 1-worker pool, what is the risk?

**Answer:** Starvation/deadlock because the sole worker is waiting on work that needs that exact worker to run.

**Question 10.** If a pipeline only performs tiny, non-blocking transforms with no affinity requirements, must every step use Async?

**Answer:** No. Non-async can reduce scheduling overhead, provided you understand the callback may run on the upstream-completing thread.

**Question 11.** How do **whenCompleteAsync** and **handleAsync** differ?

**Answer:** `whenComplete` mainly observes the outcome and normally preserves the prior outcome, whereas `handle` can compute a new result from either success or exception.

**Question 12.** If **@Async** is rejected by the executor right at the proxy call, will an **exceptionally** handler attached to the future definitely receive the error?

**Answer:** No. In some cases the call has not even returned a `Future` to attach a handler to; handle errors both at the submission boundary and on the future if returned.

**Question 13.** Does **orTimeout** guarantee a task calling an HTTP client stops immediately?

**Answer:** No. A future timeout does not guarantee cancelling/aborting I/O. You need client-level timeouts/cancellation and cleanup policies.

## 20. Pipeline Design Checklist in Spring Applications

- [ ] Clearly separate **data sources** from **dependent stages**.
- [ ] For each stage, identify whether it is **CPU-bound, blocking I/O, or a tiny callback**.
- [ ] Choose **non-async** for lightweight callbacks without thread-affinity requirements where appropriate.
- [ ] Use **Async(..., executor)** at every boundary where you genuinely want to select the pool.
- [ ] Never assume a source stage's executor is inherited indefinitely.
- [ ] Distinguish **thenApply** from **thenCompose**, and the callback's executor from the executor of the future returned by the callback.
- [ ] When using **@Async("...")**, verify bean names/qualifiers, **@EnableAsync**, and calls passing through Spring proxies.
- [ ] Handle **submission/scheduling rejections** separately from task exceptions via futures.
- [ ] Do not call **join/get** waiting on nested tasks in the same bounded pool when composition is possible.
- [ ] Configure **pools, queues, max threads, and timeouts** based on downstream capacity and SLAs.
- [ ] Pass **immutable snapshots** of required request data; never share mutable singleton fields across requests.
- [ ] Propagate and clean up **MDC, SecurityContext, and tracing** properly across thread boundaries.
- [ ] Test thread identity or explicitly named workers, not just final output values.
- [ ] Use `get(timeout)`, release latches, and call `shutdown`/`awaitTermination` so tests never hang.
- [ ] If work must not be lost on restart, design a **durable job queue/outbox** instead of relying solely on `CompletableFuture`.

## Conclusion

**Async variants** of `CompletableFuture` let you control **where and how callbacks run**, while selecting an **explicit Executor** lets you intentionally partition CPU work, blocking I/O, concurrency limits, and overload handling. Non-async methods do not pick a separate worker; Async methods without an executor typically use `CompletableFuture`'s default facility, **not Spring's pool by default**.

In Spring systems, **@Async("executorName")** controls the executor for the **proxy-dispatched method body**, whereas **thenApplyAsync/thenComposeAsync/thenCombineAsync(..., executor)** controls the executor for **each dependent callback**. To avoid "async but running on the wrong pool," **assign the right Executor at every boundary you need to control**, distinguish nested stages, avoid blocking that starves workers, manage context propagation, and test with thread identities or explicitly named executors.

**Recommended official documentation:**

- Java SE 17: [CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) and [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html).
- Java SE 17: [Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html), [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html).
- Spring Framework: [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html), [@Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html), [ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
