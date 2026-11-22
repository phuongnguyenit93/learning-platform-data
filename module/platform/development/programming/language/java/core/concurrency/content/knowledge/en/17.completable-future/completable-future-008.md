# applyToEither() and acceptEither() When Competing for Results in Java CompletableFuture

> **Scope:** Java SE 17, **CompletableFuture** topic group, focusing on coordinating two competing asynchronous sources to provide a result. This article accurately explains `applyToEither`, `acceptEither`, and their `Async` variants, normal/exceptional completion, callbacks, executors, cancellation, timeouts, side effects, and how to design a custom "first successful" helper when needed. This covers **general Java concurrency**; no Spring-specific APIs are used because Spring has its own chapter.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Clearly state that `applyToEither` returns a **transformed** result via `Function<T,U>`, whereas `acceptEither` executes a `Consumer<T>` and returns `CompletableFuture<Void>`.
2. Understand that these methods operate based on **one of the two stages completing normally**, which is **not synonymous** with a selector that always waits for the "first success" under every race involving failures.
3. Distinguish between normal completion, completion with an exception, cancellation, and timeout of the sources.
4. Understand that a callback may run on the thread that completes the source or the thread that registers the callback; `Async` variants can use the common pool or a specified executor.
5. Know that the other source is **not automatically canceled** and can still execute side effects after the dependent has completed.
6. Avoid confusing `applyToEither` with `thenCombine`, `thenAcceptBoth`, `anyOf`, `runAfterEither`, and `CompletableFuture.allOf`.
7. Use `ExecutorService`, deadlines, logging, and exception policies to coordinate two parallel calls without blocking in the wrong place.
8. Test on Java 17 using `complete(...)`/`completeExceptionally(...)` to create deterministic ordering schedules without relying on `Thread.sleep`.
9. Build a custom helper with **first successful, fail only when both sources fail** semantics when that is the actual requirement.
10. Recognize the boundaries of a completion stage: the fact that a source future has completed does not mean an external transaction outside the JVM has committed, and canceling a Future does not guarantee stopping the underlying thread/HTTP call.

**Key takeaway:** when one of the two sources completes normally and triggers the combinator, `applyToEither` produces a transformed result while `acceptEither` produces a `Void` stage after the consumer runs. However, with **competing exceptional completions**, you need to check the contract/tests of the JDK in use and **not treat either-combinators as absolute first-success failover**.

## 2. Real-World Scenario: Two Sources Returning the Same Data

Suppose an application has two independent data providers:

- Source A may return a configuration, inventory value, or metadata.
- Source B may return the same type of data from another region.
- You want to **use whichever result arrives first** instead of always waiting for both.
- Sometimes you want to **transform** the result into a new object.
- Sometimes you only want to **consume** the result to log it, record a metric, or forward it to another channel.

If the results have the same type `T`, `CompletableFuture` provides a group of combinators with "either" semantics:

```java
CompletableFuture<String> left = fetchFromLeft();
CompletableFuture<String> right = fetchFromRight();

CompletableFuture<Integer> length =
        left.applyToEither(right, String::length);

CompletableFuture<Void> published =
        left.acceptEither(right, this::publishValue);
```

This is an **illustrative snippet inside a method**: `fetchFromLeft`, `fetchFromRight`, and `publishValue` are defined by the application. It is not a standalone Java file; imports and a `this` object with appropriate methods are required.

When one source **is selected and completes normally**, the dependent stage runs the corresponding callback. `length` provides an integer; `published` holds no business value because its result type is `Void`.

### Warning About What "Fastest Source" Means

"Arriving first" refers to the **completion order observed in a single execution**, not a fixed ranking of providers. Two futures can complete almost simultaneously. If both have already completed before the callback is registered, do not write business rules that depend on "always picking the left side" or "always picking the smallest timestamp." These methods are not designed as timestamp comparators.

## 3. API Signatures of the Two Methods

Simplified signatures on `CompletionStage<T>` / `CompletableFuture<T>`:

```java
<U> CompletableFuture<U> applyToEither(
        CompletionStage<? extends T> other,
        Function<? super T, U> fn);

CompletableFuture<Void> acceptEither(
        CompletionStage<? extends T> other,
        Consumer<? super T> action);
```

These are **illustrative API signatures**, not code redeclaring methods in a project. When called on `CompletableFuture`, the return type is `CompletableFuture<U>` or `CompletableFuture<Void>` corresponding to the API class.

- `T`: the value type provided by both sources, compatible with `this` stage.
- `U`: the result type **after transformation** by `Function<T,U>`.
- `CompletionStage<? extends T> other`: the second source whose value type can be used as `T`.
- `Function<? super T,U>`: takes a `T` result and **returns `U`**.
- `Consumer<? super T>`: takes a `T` result and **does not return `U`**.
- The return type is a **dependent `CompletableFuture`**, not one of the two original futures themselves.

**Important note:** because these methods are instance methods, `left.applyToEither(right, fn)` creates a new stage. It **does not merge the `left` and `right` objects into a single shared future that controls the lifecycle of both**. The two sources can continue independently.

## 4. applyToEither(): Transforming Data from the Selected Source

Example:

```java
CompletableFuture<String> primary = new CompletableFuture<>();
CompletableFuture<String> backup = new CompletableFuture<>();

CompletableFuture<String> result = primary.applyToEither(
        backup, value -> "hello " + value);

backup.complete("B");
primary.complete("A");
System.out.println(result.join()); // hello B
```

This is a **snippet inside a method**, requiring the `CompletableFuture` import. The completion schedule is actively controlled by `main`: `backup.complete("B")` is called before `primary.complete("A")`, so the dependent receives the backup value. The callback can run immediately inside the `complete` call on the `main` thread without needing another thread.

### What Is Guaranteed?

When a source completes normally and the dependent callback is successfully triggered:

1. The `Function` receives the value of the selected source.
2. If the `Function` returns `U` normally, the dependent completes with `U`.
3. `result.join()` returns `U` or throws an exception if the dependent completed exceptionally.
4. The other source is not automatically canceled; it can still complete later.
5. Completion of the dependent and completion of the two sources are **distinct** events.

### The Function Can Throw an Error

```java
CompletableFuture<Integer> parsed = primary.applyToEither(
        backup, Integer::parseInt);
```

This is illustrative code if both sources are `CompletableFuture<String>`. When the selected source returns a non-numeric string, `NumberFormatException` from `Integer.parseInt` causes the dependent to complete exceptionally. A source completing normally **does not turn a transformation error into a success**.

This is why you must distinguish between an error in the **data source** and an error in the **data-transformation callback**. If the callback needs to validate before accepting, you can explicitly convert to a success/failure outcome according to business rules, but do not assume `applyToEither` automatically retries the callback with the other source's value when the first callback throws an exception.

### Is Returning null from the Function Valid?

Yes. `CompletableFuture<U>` can complete normally with `null` when the function returns `null`. Unlike `ConcurrentHashMap`, `CompletableFuture` does not forbid `null` as a result. However, if business code needs to distinguish between "not found" and "not yet completed," use `Optional<U>` or an explicit result type rather than inferring it from `join()` returning `null`.

## 5. acceptEither(): Processing the Result Without Producing a New U

Example:

```java
CompletableFuture<String> primary = new CompletableFuture<>();
CompletableFuture<String> backup = new CompletableFuture<>();

AtomicReference<String> consumed = new AtomicReference<>();
CompletableFuture<Void> done =
        primary.acceptEither(backup, consumed::set);

backup.complete("B");
done.join();
System.out.println(consumed.get()); // B
```

This is a **snippet inside a method**, importing `CompletableFuture` and `AtomicReference`. `Consumer<String>` writes the value into a holder; the dependent `done` has type `CompletableFuture<Void>`.

**Do not write `String answer = done.join()`.** `done.join()` has type `Void`, which normally returns `null`, not the string `"B"` itself.

### Side Effects of Consumer

`acceptEither` is commonly used for side effects:

- Sending data to another pipeline.
- Updating UI state via an appropriate executor.
- Logging the first received result.
- Incrementing a metric/counter or writing a record.

However, the callback executes on a thread determined by the semantics of the dependent stage, **not an exactly-once transaction with systems outside the JVM**. If the `Consumer` sends a message and then throws an exception due to a network timeout, the dependent may fail even though the message was actually processed by the receiver. You need an idempotency/outbox/acknowledgment policy if the work is critical.

### Consumer Throwing an Exception

```java
CompletableFuture<Void> sent = primary.acceptEither(
        backup, value -> {
            if (value.isBlank()) {
                throw new IllegalArgumentException("empty value");
            }
            publish(value);
        });
```

This is an illustrative snippet with a user-defined `publish` method. If the callback throws, the `sent` stage completes exceptionally. **Do not assume the system automatically runs the `Consumer` a second time with the losing source** just because the callback failed.

## 6. Comparing applyToEither and acceptEither

| Criterion | `applyToEither(other, fn)` | `acceptEither(other, action)` |
|---|---|---|
| Callback type | `Function<T,U>` | `Consumer<T>` |
| What does the callback return? | Value of type `U` | `void` |
| Dependent type | `CompletableFuture<U>` | `CompletableFuture<Void>` |
| Purpose | Transform/map data from the selected source | Consume data from the selected source |
| Observing completion | `join()/get()` returns `U` or error | `join()/get()` normally returns `null` or error |
| Exception from callback | Dependent completes exceptionally | Dependent completes exceptionally |
| Losing source auto-canceled? | No | No |
| Must wait for both sources by default? | No | No |
| Auto-retry on callback error? | No | No |

**Rule of thumb:** need a new output value → `applyToEither`; only need to finish a side effect and have a stage mark completion → `acceptEither`.

Do not choose `acceptEither` and store the result in a mutable field just because you are unfamiliar with `applyToEither`. If you want a pure transformation pipeline, `applyToEither` is usually clearer in intent and reduces the risk of shared mutable state.

## 7. Defining "Either" vs. "Both"

Combinators that are easy to confuse:

```java
left.applyToEither(right, mapper);
left.acceptEither(right, consumer);
left.runAfterEither(right, runnable);

left.thenCombine(right, combiner);
left.thenAcceptBoth(right, biConsumer);
left.runAfterBoth(right, runnable);
```

This is an **illustrative list of calls**, assuming compatible callbacks and futures are already defined.

- `applyToEither`: depends on one selected source, transforms the value.
- `acceptEither`: depends on one selected source, consumes the value.
- `runAfterEither`: runs a `Runnable` **without receiving a value** from the source; returns `CompletableFuture<Void>`.
- `thenCombine`: requires normal values from **both**, then `BiFunction<T,U,V>` combines them.
- `thenAcceptBoth`: requires **both** and `BiConsumer<T,U>` consumes them.
- `runAfterBoth`: runs a `Runnable` after **both** complete normally per the contract.

### Compared to anyOf()

`CompletableFuture.anyOf(left, right)` creates a `CompletableFuture<Object>` that completes when **any one source** completes — **normally or exceptionally**. If the first source fails, `anyOf` can complete exceptionally right away.

```java
CompletableFuture<Object> any =
        CompletableFuture.anyOf(left, right);
```

This is a snippet inside a method with `left`/`right` of type `CompletableFuture`. `anyOf` is not "wait for one success": you must distinguish its semantics from a first-success policy and handle casting/types because the return type is `Object`.

### Compared to allOf()

`CompletableFuture.allOf(left, right)` returns `CompletableFuture<Void>` and is used when you want to wait for two (or more) sources to finish, even when failures need to be aggregated/inspected. `allOf` does not aggregate the `T` values for you; you must read each source after the appropriate barrier.

## 8. Three Execution Variants of Each Combinator

Both have corresponding variants:

```java
left.applyToEither(right, fn);
left.applyToEitherAsync(right, fn);
left.applyToEitherAsync(right, fn, executor);

left.acceptEither(right, action);
left.acceptEitherAsync(right, action);
left.acceptEitherAsync(right, action, executor);
```

This is an **illustrative API list** (not a standalone file); `executor` must be an `Executor`.

### Non-Async Variant

The callback may run on the thread calling `complete` on one of the sources, on the thread registering the dependent if the result is already available, or on a thread participating in completion. You must not assume the callback will always run on a dedicated worker thread or a UI thread.

Therefore, a CPU-heavy or blocking-I/O callback in a non-Async `applyToEither` can prolong the `source.complete(...)` call or the callback chain.

### Async Variant Without a Specified Executor

`applyToEitherAsync(other, fn)` and `acceptEitherAsync(other, action)` typically use the default asynchronous execution facility of `CompletableFuture` (usually `ForkJoinPool.commonPool()`, unless runtime/implementation conditions noted in the Javadoc apply). Do not assume this is a pool that your application shuts down or configures itself.

Do not place long-running blocking I/O on the unbounded common pool without understanding resource contention/capacity.

### Async Variant with a Custom Executor

`applyToEitherAsync(other, fn, executor)` and `acceptEitherAsync(other, action, executor)` submit the callback to the specified executor. Use this when you need workload isolation, control over thread names/capacity, or a guarantee that the callback runs in a specific execution context.

```java
ExecutorService mapperPool = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<String> result =
            left.applyToEitherAsync(right, String::trim, mapperPool);
    System.out.println(result.join());
} finally {
    mapperPool.shutdown();
}
```

This is a **snippet inside a method**, requiring imports for `ExecutorService` and `Executors`. For real-world usage, a deadline/shutdown policy is needed if the callback can block. The executor can reject tasks, causing the dependent to complete exceptionally; `Async` variants are not immune to `RejectedExecutionException` or shutdown races.

**Common misconception:** the word "Async" primarily governs where/when the callback is dispatched; it does not make two already-async sources "more async," and it does not create automatic cancellation propagation.

## 9. Runnable Java 17 Example: Normal Win, Async, Exception, Cancellation

The complete program below drives two sources using `CompletableFuture` instances completed manually to **create a deterministic schedule**. It then tests the `Async` variant on an executor named `either-worker`, the scenario where one source fails first, and the fact that the losing source is not automatically canceled.

Create the file **`EitherCombinatorsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class EitherCombinatorsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> primary = new CompletableFuture<>();
        CompletableFuture<String> fallback = new CompletableFuture<>();
        AtomicReference<String> consumed = new AtomicReference<>("none");

        CompletableFuture<String> converted = primary.applyToEither(
                fallback, value -> "mapped=" + value.toUpperCase());
        CompletableFuture<Void> observed = primary.acceptEither(
                fallback, value -> consumed.set("accepted=" + value));

        fallback.complete("backup");
        primary.complete("primary");
        System.out.println(converted.join());
        observed.join();
        System.out.println(consumed.get());
        System.out.println("primaryValue=" + primary.join());

        ExecutorService custom = Executors.newSingleThreadExecutor(
                job -> new Thread(job, "either-worker"));
        try {
            CompletableFuture<String> left = new CompletableFuture<>();
            CompletableFuture<String> right = new CompletableFuture<>();
            CompletableFuture<String> async = left.applyToEitherAsync(
                    right, value -> value + "@" + Thread.currentThread().getName(), custom);
            right.complete("fast");
            System.out.println("async=" + async.join());
            left.complete("slow");
        } finally {
            custom.shutdown();
        }

        CompletableFuture<String> broken = new CompletableFuture<>();
        CompletableFuture<String> eventual = new CompletableFuture<>();
        CompletableFuture<String> dependent =
                broken.applyToEither(eventual, value -> "ok:" + value);
        broken.completeExceptionally(new IllegalArgumentException("first failed"));
        System.out.println("earlyExceptional=" + dependent.isCompletedExceptionally());
        eventual.complete("later success");
        try {
            System.out.println(dependent.join());
        } catch (CompletionException ex) {
            System.out.println("failureCause=" + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("eventualValue=" + eventual.join());

        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        CompletableFuture<Void> notifier = first.acceptEither(second, s -> { });
        first.complete("done");
        notifier.join();
        System.out.println("acceptResultIsVoid=" + (notifier.join() == null));
        System.out.println("otherStillPending=" + !second.isDone());
        second.cancel(false);
        System.out.println("otherCancelled=" + second.isCancelled());
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 EitherCombinatorsDemo.java
java EitherCombinatorsDemo
```

**Actual verified Java 17 stdout:**

```text
mapped=BACKUP
accepted=backup
primaryValue=primary
async=fast@either-worker
earlyExceptional=true
failureCause=IllegalArgumentException
eventualValue=later success
acceptResultIsVoid=true
otherStillPending=true
otherCancelled=true
```

### Analyzing the Normal Result Selection

`fallback.complete("backup")` happens before `primary.complete("primary")`, and both callbacks were registered beforehand. Thus `converted` uses `backup` and transforms it to `mapped=BACKUP`, while `observed` records `accepted=backup`.

After `fallback` has won, `primary` can still be completed with `"primary"`, and `primary.join()` produces `primaryValue=primary`. The dependent result **does not change when the losing value arrives later**.

### Analyzing Async with a Specified Executor

`left.applyToEitherAsync(right, ..., custom)` uses the `custom` executor when executing the callback. `right.complete("fast")` is called before `left.complete("slow")`; the callback returns a string with the thread name appended. Because the executor has a named `ThreadFactory`, the output `async=fast@either-worker` is the verified result.

**Do not conclude that every Async call always runs on a thread with this name.** This thread name was **created by the example itself**. In another application, the executor/thread name depends on configuration.

### Analyzing Source Exceptions

`broken.completeExceptionally(new IllegalArgumentException(...))` is called **before** `eventual` completes. On the tested Java 17 runtime, the `applyToEither` dependent already completed exceptionally: `earlyExceptional=true`. When `eventual` completes normally afterward, the dependent **is not flipped back to success**. `join()` throws `CompletionException` with cause `IllegalArgumentException`.

This is an executable counterexample to the false assumption **"applyToEither always waits for the first successful source even if the other source has failed."** The method specification talks about normal completion triggers; for competing exceptional completions, read the contract and do not assume a failover policy it does not promise. Specific test behavior on Java 17 should also not be used to infer a strict total order for all races where both sources complete exceptionally.

### Analyzing the Losing Branch and Cancellation

`first.complete("done")` causes `notifier` to complete normally with a `Void` value, meaning `notifier.join()==null`. Meanwhile `second.isDone()==false`; it **is not automatically canceled** because another source won. The application calls `second.cancel(false)` separately and then observes `otherCancelled=true`.

Even when canceling a `CompletableFuture` succeeds, that **does not guarantee** an associated HTTP call, database query, or computation has been interrupted at the execution layer. Future cancellation and background task lifecycle must be designed separately.

## 10. "Either" Is Not "First Successful" Under Every Failure

This is the easiest part of the topic to get wrong.

Someone might define the goal as follows:

> Call two endpoints A and B. If A returns success first, use A. If A fails, **keep waiting for B**. Report an error only when **both A and B fail**.

That is a **first-success-failover policy**, which is not synonymous with the semantics you can naively assume from `applyToEither`/`acceptEither`.

### Experiment on Java 17

In the example above:

1. `broken` was completed exceptionally.
2. `dependent.isCompletedExceptionally()` became `true` immediately.
3. `eventual` later completed normally.
4. `dependent` **remained failed**, unchanged.

Therefore, the code:

```java
CompletableFuture<String> answer =
        primary.applyToEither(backup, value -> value);
```

is not a solution that guarantees "always try backup when primary fails." If the real requirement is **only fail when both sources fail**, write a helper with an explicit policy or use a dedicated, tested abstraction.

### Do Not Equate Exceptions with null/empty

A source completing **normally** with `null` or an empty string is still a **normal completion**. `applyToEither` does not know that `null`/empty means "no good data"; the callback may need to validate, but a callback throwing does not mean the stage automatically retries with the other source.

If you want to race on a **valid business result**, normalize each source into an outcome with explicit success/failure, then apply a coordinator that understands that success criterion.

## 11. Java 17 Example: Building a Custom firstSuccessful()

The helper below takes two `CompletableFuture<? extends T>` instances and completes the result on the **first normal completion**. If one source fails, the helper records the error and continues waiting for the remaining source; **only when both sources fail** does it complete the result exceptionally.

This is a **different** policy from the built-in either combinators. It is useful when you want true "success-over-failure" behavior.

Create the file **`FirstSuccessDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class FirstSuccessDemo {
    static <T> CompletableFuture<T> firstSuccessful(
            CompletableFuture<? extends T> left,
            CompletableFuture<? extends T> right) {
        CompletableFuture<T> winner = new CompletableFuture<>();
        AtomicInteger failures = new AtomicInteger();
        AtomicReference<Throwable> firstFailure = new AtomicReference<>();

        left.whenComplete((value, error) -> {
            if (error == null) {
                winner.complete(value);
            } else {
                firstFailure.compareAndSet(null, error);
                if (failures.incrementAndGet() == 2) {
                    winner.completeExceptionally(firstFailure.get());
                }
            }
        });
        right.whenComplete((value, error) -> {
            if (error == null) {
                winner.complete(value);
            } else {
                firstFailure.compareAndSet(null, error);
                if (failures.incrementAndGet() == 2) {
                    winner.completeExceptionally(firstFailure.get());
                }
            }
        });
        return winner;
    }

    public static void main(String[] args) {
        CompletableFuture<String> left = new CompletableFuture<>();
        CompletableFuture<String> right = new CompletableFuture<>();
        CompletableFuture<String> successful = firstSuccessful(left, right);
        left.completeExceptionally(new IllegalStateException("left error"));
        System.out.println("stillWaitingAfterOneFailure=" + !successful.isDone());
        right.complete("right succeeded");
        System.out.println("selected=" + successful.join());

        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();
        CompletableFuture<String> bothFailed = firstSuccessful(a, b);
        a.completeExceptionally(new IllegalArgumentException("a"));
        b.completeExceptionally(new IllegalStateException("b"));
        try {
            bothFailed.join();
        } catch (CompletionException e) {
            System.out.println("bothFailedCause=" + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 FirstSuccessDemo.java
java FirstSuccessDemo
```

**Verified stdout on Java 17:**

```text
stillWaitingAfterOneFailure=true
selected=right succeeded
bothFailedCause=IllegalArgumentException
```

### Why Does This Helper Have Different Semantics?

- Each source invokes `whenComplete` when it has an outcome, including success or failure.
- If `error == null`, the source succeeded normally, and the helper attempts `winner.complete(value)`. Only the first completion succeeds because `complete` on `CompletableFuture` is an atomic operation.
- If the source failed, the helper records the first throwable and increments `failures`. When there is only 1 failure, it **does not complete `winner`**.
- When there are 2 failures, no source can succeed anymore, so the helper calls `winner.completeExceptionally(...)`.
- If both sources succeed nearly simultaneously, both callbacks may attempt `complete`, but only one succeeds.
- If a success occurs before the other source fails, the result is already completed normally; the later failure does not change the result.

### Caveats to Know Before Production Use

1. **Does not cancel the losing source.** Like the either combinators, completing `winner` does not automatically send cancellation to the sources.
2. **No deadline attached.** If one source fails and the other hangs forever, `winner` can also wait forever. You need `orTimeout`/cancellation/I/O deadlines per your contract.
3. **Does not collect both exceptions into an aggregate.** The demo returns the first cause. If you want forensic detail, store both failures by source and build a composite exception using `addSuppressed`, while protecting ordering/ownership.
4. **A successful source can return `null`.** `error == null` is still treated as success, even when the value is `null`; if `null` is a business failure, normalize the outcome before the callback.
5. **`whenComplete` callbacks may run on the thread completing the source.** Keep logic lightweight and non-blocking; if separate scheduling is needed, consider `whenCompleteAsync` with a bounded-capacity executor.
6. **Canceling `winner` does not automatically cancel source futures**, unless you add explicit propagation policy.
7. **Source cancellation** arrives as an error and is counted by the helper as a failure. Whether that makes sense depends on the domain; a separate policy is needed if cancellation should abort the entire race.
8. **Limited to 2 sources.** For N sources, you need a participant-aware counter and aggregated error handling; do not assume a two-source helper scales properly when copy-pasted.
9. **No exactly-once side effects** for external calls; the non-winning source may still have written data externally.

This pattern illustrates **first-success orchestration**. Production deployment requires appropriate monitoring, timeouts, thread pool capacity, exception policies, and cleanup.

## 12. How Do Normal and Exceptional Completions Affect Behavior?

A `CompletableFuture<T>` can be:

- Completed normally with `T`.
- Completed normally with `null`.
- Completed exceptionally with a throwable.
- Canceled, which is a form of exceptional completion.
- Incomplete; possibly still running or waiting on I/O or a queue.

### One Source Normal First

When `left.complete(value)` is the event that causes the dependent to select a normal result, the callback can be triggered. If the callback returns normally, the dependent completes normally. The other source does not need to complete before the dependent has a result.

### One Source Exceptional First

**Do not assume** the dependent will wait for the other source to succeed. The Java 17 example in this article confirms that an `applyToEither` dependent can complete exceptionally early. Test the specific JDK behavior if your policy depends on exception-race details, and if true failover is required, use a helper with an explicit contract.

### Both Sources Exceptional

The dependent has no normal value to pass to the `Function`/`Consumer`. It can complete exceptionally. **Do not assume which throwable is chosen—left, right, or whichever failed first—across all competing schedules**. If you need both errors, observe them individually with `handle`/`whenComplete` instead of only reading the dependent's exception.

### Callback Throws an Exception

Even when a source has completed normally, the callback can fail and cause the dependent to complete exceptionally. Two classes of failures should be separated in logs:

- Source failure: HTTP request, computation, or source validation.
- Dependent callback failure: mapping/conversion/consumer side effect.

### Cancellation

Calling `future.cancel(true)` on a `CompletableFuture` completes it with a `CancellationException`; per the `CompletableFuture` API, the `mayInterruptIfRunning` parameter **has no interrupt-control effect** on `CompletableFuture` as it does on some `FutureTask` implementations. Do not infer from `cancel(true)` that an underlying HTTP client thread is interrupted.

## 13. get(), join(), CompletionException, and ExecutionException

After creating a dependent:

```java
CompletableFuture<Integer> mapped = left.applyToEither(
        right, String::length);
```

This is a snippet inside a method, with `left`/`right` as `String` futures.

Ways to retrieve the result:

- `mapped.join()`: waits and returns `Integer`; if the dependent failed, typically throws `CompletionException` wrapping the cause; if canceled, may throw `CancellationException`.
- `mapped.get()`: waits and returns `Integer`; if failed, throws `ExecutionException`; if canceled, throws `CancellationException`; the method declares checked `InterruptedException`.
- `mapped.get(timeout, unit)`: may throw `TimeoutException`; **a timeout on `get` does not automatically cancel the future**.
- `mapped.isDone()`: `true` on success, failure, or cancellation; does not assert a valid result.
- `mapped.isCompletedExceptionally()`: `true` when completed exceptionally, including cancellation.
- `mapped.isCancelled()`: reflects only the canceled state of that future itself per its contract.

### Where to Catch Exceptions?

```java
try {
    int size = mapped.get(2, TimeUnit.SECONDS);
    use(size);
} catch (TimeoutException e) {
    onTimeout(e);
} catch (ExecutionException e) {
    onFailure(e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    onInterrupted(e);
}
```

This is illustrative code with `mapped`, `use`, `onTimeout`, `onFailure`, and `onInterrupted` supplied by the caller; you may also need to handle unchecked `CancellationException` if cancellation is valid in the workflow.

**Note:** canceling the dependent does not guarantee canceling upstream work. A `get` timeout does not perform cancellation either. Handle "caller no longer wants to wait" and "source operation needs to stop" separately.

## 14. Real Race: Two HTTP Calls—Which One Wins?

An application may run two HTTP calls in parallel:

```java
CompletableFuture<Payload> east =
        CompletableFuture.supplyAsync(() -> fetchEast(), ioExecutor);
CompletableFuture<Payload> west =
        CompletableFuture.supplyAsync(() -> fetchWest(), ioExecutor);

CompletableFuture<Response> result =
        east.applyToEither(west, payload -> validateAndConvert(payload));
```

This is an **illustrative snippet**, requiring types/methods `Payload`, `Response`, `fetchEast`, `fetchWest`, `validateAndConvert`, and `ioExecutor`. `supplyAsync` dispatches the suppliers to the executor, while non-Async `applyToEither` may execute the callback on the thread completing the winning source.

### Decisions the Application Must Make Itself

- If both HTTP calls return 200 with valid data, the value observed by the combinator in the race is chosen.
- If one call fails first and the other succeeds later, **do not assume** the built-in either combinator guarantees the success wins; use a custom first-success policy if that is a requirement.
- If an endpoint returns stale/invalid data but completes normally, the combinator cannot tell it is low quality; validate before racing or use custom outcome orchestration.
- If the mapping callback triggers a side effect, do not treat "whichever returned first" as a transaction guaranteeing the side effect was never executed for the other source.
- If a slow source keeps running, it can consume connections, CPU, memory, and downstream quota after the result is already available.
- If you need to cancel the loser, use the actual HTTP client/task API and understand its cancellation semantics; `CompletableFuture.cancel` is not always sufficient.
- If endpoints have rate limits, running two calls concurrently for every request can **double the load**. Measure the cost/latency tradeoff.

## 15. Hedged Requests and Speculative Execution

A "hedged request" sends a second request to reduce tail latency if the first request is slow. The idea is related to either-combinators, though not identical:

- **Immediate parallel race:** dispatch both A and B at the same time; lower latency when one source is fast, but nearly double the cost.
- **Delayed hedge:** send A first, only send B if A has not completed after a threshold; requires a separate timer, cancellation, and coordinator.
- **First-success:** if A fails, wait for B to potentially succeed; requires a policy for exceptional completions like the helper above.
- **First-completion:** whichever result or error arrives first wins; closer to `anyOf`, not necessarily the desired policy.
- **First-valid-response:** only choose a response that passes validation; requires coordinating validation with failure counts and timeouts.

`applyToEither`/`acceptEither` only solve part of **dependent stage execution**. Production hedging also needs retry budgets, idempotency, overload protection, deadlines, observability, and a decision on handling the loser.

### Example About Side Effects

Do not use two speculative operations that debit money or deduct inventory on the same business entity and assume "only the first result is read" means the losing operation is rolled back. If both sources executed their side effects, both may commit. Using races for **read-only/idempotent requests** is a safer starting point, after which you can evaluate the domain contract.

## 16. Which Thread Runs the Callback?

This is a critical question for performance and deadlocks.

### Non-Async

`applyToEither(other, fn)` and `acceptEither(other, consumer)` do not promise to run the callback on a pool you chose. For example, a thread calling `fallback.complete(...)` may simultaneously run the dependent callback inline on the completion path.

If the callback calls `Thread.sleep`, queries a database, or waits on another Future, the thread completing the source can be occupied for a long time. With a single-thread executor, a callback waiting on a task that needs that very same executor can cause a **thread starvation deadlock**.

### Async Without a Specified Executor

The default asynchronous execution facility may use the common pool. If the callback runs long I/O and the common pool has other computations, you can cause contention/starvation. When workloads need isolation, use a dedicated executor.

### Async with an Executor

`applyToEitherAsync(other, fn, executor)` decouples the callback from the thread completing the source, but you must:

- Configure worker count, queue capacity, and rejection policy.
- Proactively shut down application-owned executors.
- Avoid waiting on other tasks on the same pool that might become saturated.
- Handle callback failures/exceptions.
- Not create a new executor per request without a lifecycle owner.

### Do Not Rely on ThreadLocal as Automatically Propagated Context

Context in a `ThreadLocal` of the thread that created the future does not automatically appear in a callback running on another worker. If you need a trace ID, security context, or tenant ID, use **explicit context propagation** or an appropriate wrapper, rather than relying on whichever thread happens to run the callback.

## 17. Completion Order and Callback Order Can Differ

A dependency that easily causes bugs:

```java
CompletableFuture<String> left = ...
CompletableFuture<String> right = ...
CompletableFuture<String> mapped = left.applyToEither(right, mapper);
```

This is a pseudocode snippet placed inside a method, with `mapper` and the futures already defined.

If both sources complete very close together:

- Source completions have an actual order at the state level of each Future, but dependents have a race to claim completion.
- Do not use `mapped` to determine an "absolute order" between two network events without separate timestamp/correlation/cause tracking.
- An `applyToEither` callback and an `acceptEither` callback registered separately on the same pair of sources **do not necessarily pick the same side** when both sources complete nearly simultaneously. The main demo forced `backup` to complete first so both saw `backup`; that was determinism of the example, **not a coupling between the two combinators**.

If you need the **same winner for both transformation and consumption**, create **a single winner stage** and chain operations from it:

```java
CompletableFuture<Payload> winner =
        left.applyToEither(right, value -> value);
CompletableFuture<View> mapped = winner.thenApply(this::render);
CompletableFuture<Void> observed = winner.thenAccept(this::audit);
```

This is an illustrative snippet inside a method. Both `mapped` and `observed` receive the same source result chosen by `winner`, though the execution order of `thenApply` and `thenAccept` **is not guaranteed** if registered separately. If you need `audit` only after `render`, chain them with an explicit dependency.

## 18. acceptEitherAsync and UI/Event Loops

If a callback updates the UI, ensure the executor matches the UI framework or event loop; do not call UI code from an arbitrary common-pool thread. `acceptEitherAsync(other, action, uiExecutor)` can be appropriate if the framework actually provides an `Executor` representing the UI thread.

Example in console Java:

```java
ExecutorService consumerExecutor =
        Executors.newSingleThreadExecutor();
try {
    CompletableFuture<Void> processed =
            left.acceptEitherAsync(right, this::consume, consumerExecutor);
    processed.join();
} finally {
    consumerExecutor.shutdown();
}
```

This is illustrative code, not tied to any UI framework or Spring. `this::consume` is a method defined by the class. In a long-lived application, reuse the executor instead of creating and shutting it down per callback.

**Do not make the event loop/UI thread block with `join()`** if the source also needs that event loop to complete; that can deadlock. Register a continuation and return control to the event loop instead of blocking.

## 19. Timeout for the Entire Race

An either-dependent can hang if neither source makes progress and there is no timeout/cancellation policy.

`CompletableFuture` provides:

- `orTimeout(timeout, unit)`: can complete the future exceptionally with `TimeoutException` when the deadline passes.
- `completeOnTimeout(value, timeout, unit)`: can complete normally with a fallback value on timeout.
- `get(timeout, unit)`: the timeout only limits **how long the caller waits**, it does not complete the future itself.
- `cancel(...)`: marks completion by cancellation, which is not synonymous with stopping underlying work.

Example:

```java
CompletableFuture<String> raced =
        primary.applyToEither(backup, value -> value);
raced.orTimeout(250, TimeUnit.MILLISECONDS);
```

This is illustrative code; the unit/time budget is just an example. `orTimeout` **mutates the same future** it is called on (returning that reference); it does not create a transaction timeout for both upstream sources. After `raced` times out, `primary`/`backup` may still keep running.

### End-to-End Deadline

A request with a 250 ms deadline may need:

1. Deadlines on the source I/O operations, not just `Future.get`.
2. A deadline on the dependent/winner.
3. Cancellation/cleanup of losers if supported by the platform.
4. Metrics distinguishing timeouts, source failures, and callback failures.
5. Backpressure to prevent pool queues from accumulating work after the user has already timed out.

Do not put a separate timeout on every stage and add them up into a chain that exceeds the end-to-end SLO.

## 20. Canceling the Losing Source: Must Be Done Explicitly with a Policy

After a winner is chosen, an application may try to cancel the loser to save resources. However, you must distinguish:

- `CompletableFuture.cancel(true)` marks the future as canceled and its dependents may complete exceptionally, **without guaranteeing interruption of the underlying computation**.
- A task started via `ExecutorService.submit` returns a `FutureTask`; `FutureTask.cancel(true)` can request an interrupt if the task is running. That is a different handle from the `CompletableFuture` returned by `supplyAsync`.
- An HTTP client/network library may support cancellation via its own request handle/token; actual behavior depends on the client.
- If the loser has already executed a side effect, canceling does not roll it back.
- If the loser has already completed, calling `cancel` normally does not change the result.
- If both sources share an upstream computation, indiscriminately canceling the loser can break other consumers.

**Do not blindly write `winner.thenRun(() -> { left.cancel(true); right.cancel(true); })`** because it can attempt to cancel the winning source too (even though it already completed) and affect other dependents. You need to know exactly which source won and who owns each source, and decide whether cancellation is valid.

If you want to track winner identity, you can wrap each source in an immutable outcome object before racing—for example `record Sourced<T>(String source, T value) {}`—and then inspect `candidate.source` rather than guessing.

## 21. Exception Handling: exceptionally(), handle(), whenComplete()

You can chain onto the dependent:

```java
CompletableFuture<Integer> mapped =
        left.applyToEither(right, String::length);

CompletableFuture<Integer> recovered =
        mapped.exceptionally(error -> 0);
```

This is illustrative code, with `left`/`right` of type `CompletableFuture<String>`. If `mapped` fails, `recovered` can return `0`; however, this **does not automatically retry the losing source**. `exceptionally` only provides a way to turn a failed outcome into a fallback for the next stage.

### handle()

`handle((value, error) -> ...)` runs for both normal and exceptional outcomes and can convert them into a unified result type:

```java
CompletableFuture<String> description = mapped.handle(
        (size, error) -> error == null
                ? "size=" + size
                : "failed=" + error.getClass().getSimpleName());
```

This is a snippet inside a method. `error` may be a `CompletionException` wrapper; obtaining the root cause requires careful unwrapping per your policy. `handle` does not automatically pick another source to retry.

### whenComplete()

`whenComplete((value, error) -> ...)` is suitable when you need outcome metrics/logging, typically preserving the original outcome (unless the action itself throws an exception per the contract) instead of transforming it into another type.

```java
CompletableFuture<String> observed = result.whenComplete(
        (value, error) -> logOutcome(value, error));
```

This is a snippet where `logOutcome` is defined. If the logging function throws an exception, the dependent observational stage can complete exceptionally. Do not put long blocking I/O or secrets into telemetry callbacks.

### Do Not Recover with a Fallback That Swallows Business Errors

If the business contract is "only use validated data," an unconditional `exceptionally(error -> defaultValue)` can hide critical errors. A fallback must have appropriate provenance and freshness status. Record metrics identifying which source failed, the cause, and whether the fallback used was valid.

## 22. Scope of the Java Memory Model and Visibility

`CompletableFuture` is a completion mechanism with synchronization. When a stage completes normally after producing a result, the dependent stage and the thread calling `join()/get()` observe state according to the memory consistency contract associated with `Future`/completion.

However:

- Two suppliers both mutating a shared `int counter++` can race **before the either-combinator selects a winner**. Completion does not fix lost updates.
- If sources return a reference to a mutable object that other threads continue modifying, the dependent callback does not automatically protect against future mutations. Prefer immutable DTOs/records or explicit ownership/locks.
- `thenApply`/`acceptEither` does not turn a database write plus Future completion into an atomic distributed transaction.
- The demo's `AtomicReference` holds the consumed state safely; `observed.join()` waits for the callback to finish before `main` reads it.
- If two independent either-combinators are registered, there is no shared linearization point forcing both to read the same value in every near-simultaneous race.

### Immutable Result Illustration

```java
record Price(String source, long cents) {}

CompletableFuture<Price> first = ...;
CompletableFuture<Price> second = ...;

CompletableFuture<Long> cheapestAvailableSoon =
        first.applyToEither(second, Price::cents);
```

This is illustrative code. The name `cheapestAvailableSoon` is **semantically inaccurate**: the price returned is from whichever source completes first, not necessarily the cheapest price. Name it `firstAvailablePrice` if that is the intent. If you want the **minimum price**, you must wait for both and use `thenCombine` to compare.

## 23. Limitations When a Source Completes Early with Bad Data

A source may complete normally with parseable but stale JSON. `applyToEither` selects it by completion, while the callback checks freshness, finds it invalid, and throws. There is no built-in guarantee that the other source will automatically be retried as an alternative.

Two approaches:

1. **Validate inside each source pipeline** so the source's output is a failed future if the data is invalid, then use a **`firstSuccessful` helper** like the one above.
2. **Use an outcome coordinator** that receives `Result.Success(value)`/`Result.Failure(error)`, only completing the winner on a `Success` and aggregating `Failure`s when no sources remain.

Do not turn an invalid value into `null` and expect the either-combinator to skip it; `null` is still a normal completion of `CompletableFuture`.

### Business Tie-Breaking

If two sources succeed nearly simultaneously and you need to prefer `primary` within the same deadline, an either-combinator does not promise that policy. You need an explicit decision rule based on:

- Priority level and deadline window.
- Consistently/monotonically measured timestamps.
- Data freshness/version.
- Latency budget and quality score.

A completion race does not replace a ranking algorithm.

## 24. When Should You Use thenCombine Instead of Either?

For example, when you need **both price and shipping cost**:

```java
CompletableFuture<Long> price = ...;
CompletableFuture<Long> shipping = ...;
CompletableFuture<Long> total =
        price.thenCombine(shipping, Long::sum);
```

This is illustrative code. `thenCombine` waits for both sources to complete normally and combines `price + shipping`. Using `applyToEither` here would be wrong: it only picks one of the two values, not their sum.

For example, checking that two providers agree on a version: use `thenCombine` to compare them, not `either`.

### When Should You Use anyOf?

If the requirement truly is **first completion, including errors**, `anyOf` has different semantics. However, the `Object` return type and exception handling must be defined. Do not choose `anyOf` merely to avoid deciding between `applyToEither` and `acceptEither` when you know both sources have type `T` and need mapping/consumption.

## 25. Backpressure and Resource Ownership When Racing

Running two sources concurrently typically increases work compared to running one:

- Doubling HTTP requests can raise downstream p99 latency even if the individual caller's latency drops.
- Two tasks can occupy two worker threads/connection slots.
- If the caller has timed out while sources keep running, backlogs and work queues can build up.
- The common pool can be impacted if you place blocking callbacks on it.
- Cancellation is not guaranteed to release sockets/threads/connections immediately.
- Error metrics can be lost if you only observe the dependent winner and ignore loser failures.

A production system should have:

1. Concurrency limits for speculative tasks.
2. Separate I/O timeouts and end-to-end deadlines.
3. Metrics for source A/B, winner distribution, failed/timeout/canceled counts, and callback latency.
4. Idempotency policies for repeated operations.
5. Circuit breakers/rate limits when a source frequently fails.
6. Ownership of executors and cancellation handles.
7. Shutdown logic ensuring no resource leaks remain.

If traffic is low and requirements are simple, a single source with sequential fallback may be better than fanning out every request. Choose racing when the latency benefit genuinely justifies the cost.

## 26. Thread Starvation Deadlock Trap

A common mistake:

```java
ExecutorService single = Executors.newSingleThreadExecutor();

CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> slowA(), single);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> slowB(), single);
CompletableFuture<String> winner =
        a.applyToEither(b, value -> value);
```

This is illustrative code; `slowA`/`slowB` need to be declared. Using a single worker means the two suppliers normally **do not run in parallel**, so there is no real race: `B` sits in the queue while `A` runs.

Worse, if a callback on that same worker calls `winner.join()` before any supplier has a worker to complete it, a thread can block while holding the only slot, leaving source tasks with no worker to make progress.

**Solution:** provision enough resource capacity for tasks that must complete concurrently, avoid calling `join()/get()` inside callbacks that depend on the same small pool, and use async continuations instead of blocking waits.

"Having two `CompletableFuture`s" **does not mean there are actually two parallel computations**, especially when both share a single-worker executor or the underlying source logic runs sequentially.

## 27. Errors When Cancellation or Timeout Happens Before Mapping

Scenario:

- The dependent is already registered.
- One source is canceled while the other source has not completed yet.
- The dependent can be affected by the exceptional outcome according to JDK behavior, rather than defaulting to "wait for the other's success."
- The caller calls `dependent.orTimeout(...)` and the dependent times out.
- The remaining source later completes normally, but the dependent has already completed exceptionally so **its result cannot be changed**.

Therefore, three separate policy layers are needed:

- **Source cancellation:** can the source operation be stopped? When?
- **Race selection:** which success/failure/timeout counts as the winning result?
- **Caller cancellation:** the caller no longer needs the result; should sources and side effects be canceled?

In the `firstSuccessful` helper, source cancellation is currently counted as a failure. If the domain wants "one source canceled => cancel entire race," the helper must be modified. Do not change semantics by guesswork after tests pass.

## 28. Debugging and Deterministic Testing

### Test Callback Values, Not Sleep

A good test creates two incomplete `CompletableFuture`s, registers the dependent, and explicitly calls `right.complete("R")` before `left.complete("L")`. Then assert the mapped value is `"R"`. No `sleep` needed, no scheduler dependency.

### Test Near-Simultaneous Completion

Use `CountDownLatch`/`CyclicBarrier` to let two threads complete close together and verify the result is **one of the two valid values**, without hard-coding which side wins. If exact priority is required, test a coordinator with explicit tie-breaking.

### Test Exception Behavior

- Source A completes exceptionally, B is pending.
- Verify the dependent outcome according to the chosen policy.
- B completes normally afterward; verify whether the dependent can change (`CompletableFuture` completes only once).
- If success-over-error is required, use the `firstSuccessful` helper and assert the dependent is still pending after A's failure and returns B after B's success.
- Both A and B fail: assert the cause/aggregate failure per contract.
- Callback throws: assert the dependent failed; do not infer that the source failed.
- Cancellation: assert the loser remains pending if not canceled, and becomes canceled only after explicit cancel.
- Timeout: verify the caller deadline and resource cleanup separately.

### Mental Race Detector

When reviewing code, ask:

1. **How many sources?** Two or N, and do they actually run in parallel?
2. **Which stage is the source?** The raw `CompletableFuture<T>` or an already transformed/validated stage?
3. **What is the winning condition?** First completion, first normal, first valid, first successful over errors, or priority-based?
4. **Why did the callback run?** Did the source complete normally, or is the dependent recovering from an exception?
5. **Where does the callback run?** Calling thread, common pool, or a dedicated executor?
6. **Who owns cancellation?** Does the winner have the right to stop the loser?
7. **Do you need exactly one side effect or just one chosen result?** Those two are different.
8. **Are timeouts, backpressure, and metrics in place?** A race does not provide them automatically.

## 29. Common Misconceptions

1. **"Both `applyToEither` and `acceptEither` return a new value `U`."** False: `acceptEither` returns `CompletableFuture<Void>`.
2. **"`applyToEither` means the faster result is always better."** No; it selects by completion, without checking business quality.
3. **"Either always waits for the first success even if the other side failed."** Do not rely on this; the Java 17 demo proves early exceptional completion of the dependent.
4. **"If the transformation callback fails, it automatically tries the other source."** No: an exception in the `Function`/`Consumer` fails the dependent.
5. **"Only the winner runs; the loser stops automatically."** False: both sources can continue executing side effects.
6. **"`CompletableFuture.cancel(true)` kills the HTTP-handling thread."** No: `mayInterruptIfRunning` has no effect on `CompletableFuture` per the API.
7. **"`Future.get(timeout)` cancels the source."** False: it only limits how long the caller waits.
8. **"`acceptEither` completing means the `Consumer` cannot throw."** If the `Consumer` throws, the dependent fails.
9. **"Async always creates a new thread."** No: it uses an executor, which may reuse workers.
10. **"Non-Async always runs on the main thread."** No; the callback can run on whichever thread completes a source.
11. **"`thenCombine` is the same as `applyToEither`."** No; `thenCombine` requires both sources to complete normally.
12. **"`anyOf` waits for the first success."** No; it can complete with the first exception.
13. **"Two either callbacks on the same sources always pick the same winner."** Not guaranteed under near-simultaneous competition; chain a single winner stage for consistency.
14. **"Once a result is ready, loser errors can be ignored without logging."** No, the loser can still fail or hold resources and needs metrics/cleanup.
15. **"A `null` value means the future has not completed."** No: `CompletableFuture` can complete normally with `null`.
16. **"Canceling the dependent automatically cancels upstream."** There is no general automatic propagation.
17. **"A successful mapped stage means external side effects committed exactly once."** False; stage completion is an in-process state.
18. **"Two source futures on a single-thread executor definitely race."** No; one task may sit in the queue.
19. **"A non-Async `Function` can do long I/O without affecting the producer thread."** False; the callback can run inline on the completion thread.
20. **"A first-success helper does not need to handle a source that hangs forever."** False; with one failure and one permanently pending source, the result stays pending forever without a timeout.
21. **"Catching an exception and returning a fallback is always right."** It can mask validation, security, or data-integrity errors.
22. **"One winner means no resources are spent on the loser."** False; fan-out can double upstream load.
23. **"Source A always wins if `applyToEither` is called on A."** No, `other` can win by completing first.
24. **"If both complete beforehand, Java always picks `left`."** Do not rely on implementation scheduling; do not use it as a tie-breaker.
25. **"Measuring race results with `Thread.sleep` reproduces all interleavings."** False; use explicit completion/latches and assert invariants.
26. **"Calling `source.complete` yourself means there is network concurrency."** No: that is how you test completion semantics deterministically.
27. **"One source failing makes the other source fail automatically."** Not by default; sources are independent stages.
28. **"Timing out the dependent times out the I/O."** No; you need deadlines on the underlying operations.
29. **"Using `join` on the UI thread is safe because `Future` is async."** False: `join` blocks if incomplete and can freeze the UI or deadlock.
30. **"`CompletionStage` methods behave identically across every Java implementation and every exceptional interleaving."** Rely only on the official API contract and your own explicitly designed policy when correctness depends on it.

## 30. Project Application Checklist

Before introducing `applyToEither` or `acceptEither` into code, verify:

- **Requirement:** produce `U` or run a `Void` side effect? Choose `Function` or `Consumer` accordingly.
- **Winner semantics:** first normal value, first completion, first valid response, or first successful after failures?
- **Failure:** does an early error in one source fail the dependent early; tested on the target JDK?
- **Data validation:** is a normal source with an invalid value considered a success?
- **Tie-break:** do near-simultaneous sources need a priority/source preference?
- **Executor:** can a synchronous callback block the completion thread? Need `Async` with a bounded executor?
- **Capacity:** do the two tasks actually run concurrently or get queued on a single worker?
- **Resources:** the loser keeps running; is valid cancellation/cleanup performed?
- **I/O deadlines:** are underlying call timeouts compatible with the end-to-end SLO?
- **Callback errors:** are `Function`/`Consumer` throws logged and handled on the dependent?
- **Context:** is trace/tenant/user context propagated intentionally?
- **Side effects:** are idempotency, acks, and transactions appropriate if `Consumer` writes data?
- **Testing:** normal left/right, callback throw, one source error, both errors, canceled, timeout, simultaneous completions?
- **Observability:** track winner distribution, loser failures, p95/p99, and speculative request cost?
- **Shutdown:** who owns the executor, and does it stop accepting work and await/clean up tasks?
- **Java version:** the samples run on JDK 17; do the APIs used exist in the deployment runtime?
- **Module scope:** apply general Java concurrency only; avoid mixing in unrelated scheduling/framework specifics.

## 31. Review Questions and Answers

**Question 1.** What is the main difference between `applyToEither` and `acceptEither`?  
**Answer:** `applyToEither` takes a `Function<T,U>` and returns `CompletableFuture<U>`; `acceptEither` takes a `Consumer<T>` and returns `CompletableFuture<Void>`.

**Question 2.** If `backup` completes normally before `primary`, must the dependent wait for `primary`?  
**Answer:** No; once `backup` is selected and the callback finishes, the dependent has a result without needing `primary` to finish first.

**Question 3.** Is the `applyToEither` callback automatically run a second time with the other source if the first callback throws an exception?  
**Answer:** There is no such retry/fallback in the contract; the dependent can complete exceptionally.

**Question 4.** When an `acceptEither` consumer finishes normally, what does `done.join()` return?  
**Answer:** A `Void` value, normally `null`; the source value is not returned from the dependent.

**Question 5.** After `applyToEither` has a winner, is the losing source automatically canceled?  
**Answer:** No; it can remain pending, running, and complete later.

**Question 6.** How does `applyToEitherAsync(other, fn, executor)` differ from the non-Async version?  
**Answer:** The callback is dispatched through the specified executor; the non-Async version may run on the thread completing the source or registering the callback.

**Question 7.** Is it correct to use `applyToEither` to get the lowest price between two providers?  
**Answer:** No. It selects by completion, not by comparing prices; use `thenCombine` if you need both to pick the minimum.

**Question 8.** Does `CompletableFuture.anyOf` always select the first success?  
**Answer:** No; it completes when any one source completes, even with an exception.

**Question 9.** One source fails early, and the other source succeeds later: is built-in `either` guaranteed to return the success?  
**Answer:** No. Java 17 testing shows the dependent can fail early; to always prefer success, use a custom `firstSuccessful` helper.

**Question 10.** When does the `firstSuccessful` helper in this article report an error?  
**Answer:** When both sources have failed. A single failure leaves the helper waiting for the remaining source.

**Question 11.** If one source fails and the other hangs forever, does the `firstSuccessful` helper complete on its own?  
**Answer:** No. You must add deadlines/timeouts/cancellation policies.

**Question 12.** Does `cancel(true)` on a `CompletableFuture` guarantee interrupting underlying work?  
**Answer:** No. Per the `CompletableFuture` API, `mayInterruptIfRunning` does not have the same effect as on `FutureTask`.

**Question 13.** Are two independent `applyToEither` and `acceptEither` callbacks guaranteed to always pick the same source?  
**Answer:** Not if the sources complete close together; to guarantee the same winner, create a single winner stage and chain callbacks from it.

**Question 14.** Does timing out on `get(100, MILLISECONDS)` automatically cancel the dependent?  
**Answer:** No; the timeout only limits how long the caller waits.

**Question 15.** Can you receive the source result directly via `acceptEither`?  
**Answer:** Not directly; the callback is a `Consumer` and the dependent type is `Void`. Use `applyToEither` if you need a return value.

**Question 16.** Does a callback throwing `IllegalArgumentException` turn a normally completed source into a failed one?  
**Answer:** No. The dependent callback stage can fail; the original source keeps its own state.

**Question 17.** Why can speculative requests degrade overall system throughput?  
**Answer:** Sending two requests instead of one increases CPU, network, connections, and downstream load, especially when losers are not stopped.

**Question 18.** How do you test the normal winner deterministically without using `sleep`?  
**Answer:** Register the dependent on two incomplete futures and call `right.complete("R")` before `left.complete("L")`; assert the dependent receives `"R"`.

**Question 19.** If a supplier returns `null`, does `CompletableFuture` treat that as a normal completion?  
**Answer:** Yes. `null` is not automatically treated as a failure; if business rules require non-null, validate explicitly.

**Question 20.** Does completion of a `CompletableFuture` guarantee an external transaction has committed?  
**Answer:** No; it is an in-process outcome. You need acks/transactions/idempotency for side effects outside the JVM.

## 32. Practice Exercises

### Exercise A — Map First, Consume After

Create two `CompletableFuture<String>` instances and register `applyToEither` to transform the string into a record `Result(String source, int length)`. Register `thenAccept` on the winner stage to log the result, ensuring both transformation and consumer use the **same winner**. Complete `backup` first and verify the output and source identity.

### Exercise B — Exceptional Loser

Register a built-in `applyToEither`, then call `completeExceptionally` on A and `complete` on B afterward. Observe the dependent state on JDK 17 and explain why it must not be treated as a first-success policy. Then replace it with `firstSuccessful` and assert the result returns B.

### Exercise C — Two Failures

Use `firstSuccessful` when both sources fail. Extend the helper to build an `AggregateFailure` storing both causes via `addSuppressed`, naming the sources and distinguishing cancellation from business errors.

### Exercise D — Timeout and Winner

Create one source that completes after a deadline (using a controlled test scheduler) and one source that hangs. Apply `orTimeout` to the dependent and verify the dependent fails with `TimeoutException`. Then verify the tardy source can still complete; consider real cancellation of the underlying I/O.

### Exercise E — Executor Overload

Use a bounded executor and an `acceptEitherAsync` callback that performs slow I/O; trigger many races to observe queue growth or rejected callbacks. Add a rejection/timeout policy so callers do not hang indefinitely.

### Exercise F — Near-Simultaneous Completions

Use two threads and a `CountDownLatch` to let A and B complete close together. Do not assert a fixed winner between A or B; only assert that the winner is in `{A, B}` and the callback is recorded consistently from a single winner stage.

### Exercise G — Business Validity

Each source returns `Response(data, isFresh)`. Design a coordinator that only selects a response with `isFresh=true`; if one response is stale, record a logic error and wait for the remaining source; if both are stale/failed, create an aggregate failure. Explain why plain `applyToEither` does not understand business validity on its own.

## 33. Official References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `applyToEither`, `acceptEither`, `Async` variants, cancellation, `orTimeout`, `completeOnTimeout`, `join`, `whenComplete`.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): completion-stage combinator contracts, normal/exceptional completions.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, `isDone`, and memory consistency.
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): where callbacks/tasks execute.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `Future`, and shutdown.
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper exception when an async pipeline completes exceptionally.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating completion-race tests.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory ordering, happens-before, and data races.

**Summary:** `applyToEither` takes a selected source result to **transform into `U`**; `acceptEither` takes a selected source result to **execute a `Consumer` and return `Void`**. Both are useful when two sources compete, but **they do not automatically cancel the loser**, do not create transactional side effects, and are not absolute first-success failover when exceptional completions occur. Define your winning policy accurately, use `Async`/executors matched to the workload, set clear deadlines/cancellations, observe exceptions, and use a **`firstSuccessful` helper** when the requirement is "wait for the first success; fail only when both sources fail."