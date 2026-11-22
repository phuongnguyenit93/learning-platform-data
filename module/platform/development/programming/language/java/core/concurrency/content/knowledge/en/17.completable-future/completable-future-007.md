# CompletableFuture.allOf() and anyOf() with Multiple Parallel Tasks

## 1. The Problem: Aggregating Multiple Asynchronous Tasks

Suppose a request needs to concurrently call three independent data sources: profile, settings, and recommendations. There are two different business requirements:

1. **All three results are required** before proceeding: this is *all* coordination.
2. **Only the first completed task is needed** to decide the next step: this is *any* coordination.

Java provides two static factory methods on `java.util.concurrent.CompletableFuture`:

~~~java
// Conceptual signatures, not a standalone program.
static CompletableFuture<Void> allOf(CompletableFuture<?>... cfs);

static CompletableFuture<Object> anyOf(CompletableFuture<?>... cfs);
~~~

- **`CompletableFuture.allOf(...)`** creates a composite Future that completes when **all** input Futures have completed. If all succeed, the composite Future completes normally with a `Void` result, meaning `join()` returns `null`. If one or more input Futures fail, the composite Future completes exceptionally per the contract.
- **`CompletableFuture.anyOf(...)`** creates a composite Future that receives the **outcome of the first Future to complete**. The outcome can be a success value, an exception, or a cancellation result represented via the exceptional completion mechanism. `anyOf` does **not** wait for the "first success" by default.
- **Both only coordinate state**: calling the factory does not create threads, does not run callables, does not set timeouts, and does not guarantee automatic cancellation of remaining tasks when the aggregate completes.

This is general **Java concurrency** knowledge using pure JDK APIs. Examples run on **Java 17+**.

### Learning Objectives

After this lesson, you will know how to:

1. Choose `allOf` or `anyOf` appropriately based on "all" vs. "first completed" requirements.
2. Create tasks using `supplyAsync/runAsync` and select an appropriate executor.
3. Retrieve individual results from each `CompletableFuture<T>` after `allOf` without unsafe casting from `Void`.
4. Explain exceptions, `CompletionException`, `ExecutionException`, and cancellation at each level.
5. Avoid treating `anyOf` as first-success; design controlled fallback or winner policies.
6. Handle timeouts, resource limits, avoid blocking workers with `join()`, and shut down executors properly.
7. Write deterministic tests using `CountDownLatch`, without relying on `Thread.sleep` to guess scheduling.

## 2. These Methods Do Not Execute Work for You

Look at these lines:

~~~java
// Java 17+ illustration, not a standalone program.
CompletableFuture<String> profile =
    CompletableFuture.supplyAsync(() -> loadProfile(), ioExecutor);

CompletableFuture<String> settings =
    CompletableFuture.supplyAsync(() -> loadSettings(), ioExecutor);

CompletableFuture<Void> both =
    CompletableFuture.allOf(profile, settings);
~~~

`supplyAsync` submits work to the executor. `allOf` only creates **a dependency** on both tasks completing; it is not responsible for calling `loadProfile()` or `loadSettings()` itself.

If both input Futures are already complete, the composite Future can complete immediately. If the inputs are waiting in a congested executor, `allOf` must wait too. Therefore, "using CompletableFuture" does not mean a program has better concurrency if you use the wrong executor or introduce a dependency cycle.

### 2.1. supplyAsync and runAsync

| API | Task return data | Resulting Future |
| --- | --- | --- |
| `supplyAsync(Supplier<T>)` | `T` | `CompletableFuture<T>` |
| `supplyAsync(Supplier<T>, executor)` | `T` | `CompletableFuture<T>` |
| `runAsync(Runnable)` | No return value | `CompletableFuture<Void>` |
| `runAsync(Runnable, executor)` | No return value | `CompletableFuture<Void>` |
| `allOf(cfs...)` | Does not combine into an array/list of values | `CompletableFuture<Void>` |
| `anyOf(cfs...)` | Outcome from one winning input | `CompletableFuture<Object>` |

If no executor is passed, async methods typically use `ForkJoinPool.commonPool()` per API/JVM policy. For long-blocking I/O, database, network, or tasks requiring concurrency limits, consider a dedicated executor with explicit worker count, queue, and shutdown.

### 2.2. "Parallel" Does Not Guarantee N Threads

Submitting N tasks does not guarantee that N tasks will run at the exact same time. A single-thread executor runs tasks sequentially; a fixed pool of size K allows at most K workers executing concurrently; the scheduler also determines exact execution timing. Only when **tasks are independent** and executor capacity is sufficient can tasks make concurrent progress.

Important: **create/submit the input Futures before waiting** if you want to leverage concurrency.

~~~java
// Can run concurrently, if the executor has enough workers.
CompletableFuture<Integer> a = supplyAsync(this::taskA, executor);
CompletableFuture<Integer> b = supplyAsync(this::taskB, executor);
CompletableFuture.allOf(a, b).join();
~~~

Do not write a sequence where you call `join()` immediately after submitting A and only then create B, if the goal is to start A and B concurrently.

## 3. allOf(): Wait for All, Without Aggregating Values

### 3.1. Success Contract

~~~text
A: RUNNING ------ SUCCESS(10) ---------+
                                       |
B: RUNNING ------------- SUCCESS(20) --+--> allOf = SUCCESS(null)
                                       |
C: RUNNING ---- SUCCESS(30) -----------+
~~~

`CompletableFuture.allOf(a, b, c)` returns `CompletableFuture<Void>`. When all inputs complete normally, `all.join()` completes normally and returns **null** because its type is `Void`.

**Do not write:**

~~~java
// WRONG return type, only illustrating a common mistake.
// List<Integer> values = CompletableFuture.allOf(a, b, c).join();
~~~

You must retrieve results from **the typed Futures themselves**: `CompletableFuture<Integer>` A, B, and C.

### 3.2. Retrieving Results After allOf

~~~java
// Java 17+ snippet, not a standalone program.
CompletableFuture<List<Integer>> combined =
    CompletableFuture.allOf(a, b, c)
        .thenApply(ignored -> List.of(a.join(), b.join(), c.join()));
~~~

Because `thenApply` (a normal-completion continuation) only runs after `allOf` completes successfully, all three `join` calls on the inputs already have their success results available. This snippet **does not depend on** a blocked thread waiting for the three tasks to continue executing at the time the continuation runs.

`List.of(...)` does not allow `null` elements; if a task can return null, use a data structure that permits null or convert the value into an explicit "no result" representation. Do not blindly use `List.of` with nullable values and then assume `allOf` failed due to concurrency.

### 3.3. Example 1 — Combining Three Typed Results (Java 17+)

Create file `AllOfValuesDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfValuesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> first =
            CompletableFuture.completedFuture(10);
        CompletableFuture<Integer> second =
            CompletableFuture.completedFuture(20);
        CompletableFuture<Integer> third =
            CompletableFuture.completedFuture(30);

        CompletableFuture<Void> all =
            CompletableFuture.allOf(first, second, third);

        CompletableFuture<List<Integer>> values =
            all.thenApply(ignored ->
                List.of(first.join(), second.join(), third.join()));

        System.out.println("all result null = "
            + (all.join() == null));
        System.out.println("values = " + values.join());
        System.out.println("sum = " +
            values.join().stream().mapToInt(Integer::intValue).sum());
    }
}
~~~

Compile/run:

~~~bash
javac AllOfValuesDemo.java
java AllOfValuesDemo
~~~

Exact stdout:

~~~text
all result null = true
values = [10, 20, 30]
sum = 60
~~~

All three Futures already succeeded before `all` was created, so there is no competing execution schedule. `all.join() == null` proves `allOf` returns `Void`, not a list containing the three values. The values are retrieved from each Future in the exact order specified by `List.of(first.join(), ...)`.

### 3.4. Result Order Is Defined by You

If task 3 finishes before task 1, `allOf` still **does not sort** results by completion order. When you write `List.of(first.join(), second.join(), third.join())`, the list has **input order 1, 2, 3**, regardless of the order in which tasks actually finished.

If you need completion order, design an event queue or a callback that records each result along with its ID as each task completes. `allOf` does not provide a "list ordered by completion time."

## 4. allOf() with Truly Concurrent Tasks

Instead of learning only from pre-completed Futures, the following example uses `ExecutorService` and `CountDownLatch` to prove that all three workers reached a checkpoint before being allowed to finish.

### Example 2 — Three Tasks Progressing Concurrently (Java 17+)

Create file `ParallelAllOfDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ParallelAllOfDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch entered = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<Integer> a =
                CompletableFuture.supplyAsync(
                    () -> calculate(1, entered, release), pool);
            CompletableFuture<Integer> b =
                CompletableFuture.supplyAsync(
                    () -> calculate(2, entered, release), pool);
            CompletableFuture<Integer> c =
                CompletableFuture.supplyAsync(
                    () -> calculate(3, entered, release), pool);

            CompletableFuture<Void> all =
                CompletableFuture.allOf(a, b, c);

            entered.await();
            System.out.println("before release = " + all.isDone());

            release.countDown();
            all.join();

            List<Integer> results = List.of(
                a.join(), b.join(), c.join());

            System.out.println("results = " + results);
            System.out.println("all done = " + all.isDone());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    static int calculate(int id, CountDownLatch entered,
            CountDownLatch release) {
        entered.countDown();

        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }

        return id * 10;
    }
}
~~~

Compile/run:

~~~bash
javac ParallelAllOfDemo.java
java ParallelAllOfDemo
~~~

Stdout when not unexpectedly interrupted:

~~~text
before release = false
results = [10, 20, 30]
all done = true
~~~

Why does the result not depend on the scheduler?

1. `newFixedThreadPool(3)` has three workers to run the three submitted tasks.
2. Each task calls `countDown()` and then waits on the `release` latch. `entered.await()` returns only when all three tasks have reached the wait point.
3. Main prints `all.isDone()` **before** counting down `release`, so no task can return a result yet and `all` must not be done.
4. After main opens the latch, tasks may finish in any order, but `all.join()` waits for all three and `List.of(a.join(), b.join(), c.join())` preserves the defined order.
5. `finally` releases the latch even if an exception occurs, preventing workers from hanging forever if main exits early; the pool is shut down per its lifecycle.

This example uses latches to prove concurrency rather than using `Thread.sleep(100)` to guess whether threads have started. If you used a pool with only **one** worker, main waiting for `entered` to reach 0 would hang, because the first worker is blocked at `release`; this is a classic example of why tests must have appropriate executor capacity.

## 5. allOf() When One or More Futures Fail

### 5.1. "allOf Fails" Does Not Automatically Cancel Other Tasks

If one input completes exceptionally, the composite Future **eventually** completes exceptionally as well. Per the `allOf` contract, it completes when **all** input Futures complete; you should not rely on "fail-fast immediately after the first error" behavior without a custom protocol.

The remaining tasks **are not automatically interrupted or cancelled just because one task failed**. If external work is still executing, it can continue consuming CPU/I/O until it finishes or is cancelled by a protocol.

~~~text
A: FAILED(error A) ------------------+
B: ------------ SUCCESS(value B) ----+--> allOf: exceptional completion
C: ---------------- SUCCESS(value C) -+
~~~

If **multiple** inputs fail, do not rely on the composite Future's selection of a single exception as a business-ordered result. To report all errors, inspect **each input Future** after knowing all have completed.

### 5.2. CompletionException and ExecutionException

With `CompletableFuture`, there are two common ways to wait:

| API | Can block if incomplete? | When Future fails |
| --- | --- | --- |
| `join()` | Yes | Throws unchecked `CompletionException` (usually wrapping the cause), or `CancellationException` in cancellation cases |
| `get()` | Yes | Throws checked `ExecutionException` (wrapping the cause); also `InterruptedException` or `CancellationException` |
| `get(timeout, unit)` | Bounded | Same as `get`, plus `TimeoutException` |
| `isCompletedExceptionally()` | Does not wait | Only indicates exceptional completion, including cancellation in many implementations; does not return the cause |

`join()` is convenient in composition, **but it does not make exceptions disappear**. Do not catch `CompletionException` with an empty block and pretend processing succeeded; classify the cause, compensate resources, and report the proper status if the business logic requires it.

### 5.3. Example 3 — allOf Fails While Good Tasks Keep Their Results (Java 17+)

Create file `AllOfFailureDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllOfFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> failed =
            CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid A"));
        CompletableFuture<Integer> good =
            CompletableFuture.completedFuture(20);

        CompletableFuture<Void> all =
            CompletableFuture.allOf(failed, good);

        try {
            all.join();
        } catch (CompletionException ex) {
            System.out.println("all failed cause = "
                + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("good result = " + good.join());
        System.out.println("failed exceptional = "
            + failed.isCompletedExceptionally());
        System.out.println("good exceptional = "
            + good.isCompletedExceptionally());
    }
}
~~~

Compile/run:

~~~bash
javac AllOfFailureDemo.java
java AllOfFailureDemo
~~~

Stdout:

~~~text
all failed cause = IllegalArgumentException
good result = 20
failed exceptional = true
good exceptional = false
~~~

`allOf` only aggregates completion status; it does not erase the value of `good` and does not turn all inputs into FAILED. After `all` has completed, you can classify each Future: one failed and one succeeded.

If you need **partial success** (using good results even when some tasks fail), design an explicit outcome type instead of just calling `all.join()` and discarding all results when an exception is thrown.

## 6. Collecting Full Outcomes Instead of Giving Up on the First Error

A pipeline often needs to report "3 tasks: 2 succeeded, 1 failed" rather than just a single exception.

### 6.1. Turning Errors into Typed Values

In Java 17, we can define a record type:

~~~java
// Java 17+ concept, not a standalone program.
record Outcome<T>(T value, Throwable error) {
    boolean success() {
        return error == null;
    }
}
~~~

Each Future is transformed via `handle((value, error) -> new Outcome<>(...))`. `handle` runs for both normal and exceptional completions, so the Futures wrapping `Outcome` complete **normally** even if the original task failed; `allOf` on those Outcome Futures can then be used to wait for **all** of them and collect a list without losing failure details.

~~~java
// Java 17+ snippet, not a standalone program.
CompletableFuture<Outcome<Integer>> safeA =
    originalA.handle((value, error) -> new Outcome<>(value, error));

CompletableFuture<Outcome<Integer>> safeB =
    originalB.handle((value, error) -> new Outcome<>(value, error));

CompletableFuture<Void> all =
    CompletableFuture.allOf(safeA, safeB);

CompletableFuture<List<Outcome<Integer>>> results =
    all.thenApply(unused -> List.of(safeA.join(), safeB.join()));
~~~

Be careful: `error` may be a `CompletionException` wrapping the cause; if you need to display the root cause, unwrap it in a controlled manner. If `handle` itself throws an exception while creating the Outcome or logging, the wrapper Future can still fail; do not treat `handle` as an "error-proof barrier."

### 6.2. Errors Should Not Become Fake Success Values

A bad pattern is `exceptionally(error -> 0)` for every error and then treating 0 as real data. This **hides** the distinction between "actual result is 0" and "task failed." If you want a fallback of 0, define it as an intentional business policy and record the separate outcome when auditing is needed.

A good aggregation protocol typically has labels: `SUCCESS(value)`, `FAILED(cause)`, `CANCELLED`, `TIMED_OUT` (if you actively classify timeouts). Do not conflate these cases using an ambiguous `null` or integer sentinel.

## 7. anyOf(): The Winner Is the First to Complete, Not the First to Succeed

### 7.1. Key Contract

~~~text
Task A: ------ SUCCESS("A") ----------------
Task B: -- FAILED(error B) -----------------
Task C: --------- SUCCESS("C") -------------

anyOf(A, B, C) can FAIL with B,
because B completed first, even though A/C may succeed later.
~~~

`anyOf` completes when **any** input Future completes. If the winning input succeeds with value `v`, the composite Future succeeds with `v`. If the winning input fails, the composite Future also completes exceptionally.

**Do not interpret `anyOf` as "first non-null", "first valid", "first successful", "fastest HTTP 200", or "fastest successful replica".** Those policies require filtering logic or continuing to wait when a failure occurs.

### 7.2. Why Does It Return CompletableFuture<Object>?

Input Futures can have different types:

~~~java
// Java snippet, not a standalone program.
CompletableFuture<Integer> price = ...;
CompletableFuture<String> label = ...;

CompletableFuture<Object> winner =
    CompletableFuture.anyOf(price, label);
~~~

Because it is unknown which input will complete first, the API returns `Object`. Directly casting `(String) winner.join()` is unsafe if `price` wins with an `Integer`.

Even if all inputs have the same type `String`, you still receive `CompletableFuture<Object>`. You can use `thenApply(String.class::cast)` after ensuring every successful input returns `String`, or wrap the result in a record with a type/source ID.

### 7.3. Example 4 — Deterministically Selecting the First to Complete (Java 17+)

To observe the semantics clearly without relying on a race, we control completion manually.

Create file `AnyOfWinnerDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class AnyOfWinnerDemo {
    public static void main(String[] args) {
        CompletableFuture<String> slow = new CompletableFuture<>();
        CompletableFuture<String> fast = new CompletableFuture<>();

        CompletableFuture<Object> winner =
            CompletableFuture.anyOf(slow, fast);

        fast.complete("fast");
        slow.complete("slow");

        System.out.println("winner = " + winner.join());
        System.out.println("slow = " + slow.join());
        System.out.println("fast = " + fast.join());
    }
}
~~~

Compile/run:

~~~bash
javac AnyOfWinnerDemo.java
java AnyOfWinnerDemo
~~~

Stdout:

~~~text
winner = fast
slow = slow
fast = fast
~~~

`fast.complete("fast")` happens before `slow.complete("slow")` on the same thread, so `anyOf` receives the winning result. `slow` completing afterward does not change the value of the already-terminal composite Future.

**Note:** This example **enforces completion order**; it does not pretend to prove one thread is actually faster than another. In real parallel workloads, who completes first is determined by processing time, scheduling, I/O, and errors.

## 8. anyOf() and Exceptions: A Fast Error Can Win

### Example 5 — The First Failing Future Wins the Race (Java 17+)

Create file `AnyOfFailureDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AnyOfFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> bad = new CompletableFuture<>();
        CompletableFuture<Integer> good = new CompletableFuture<>();

        CompletableFuture<Object> winner =
            CompletableFuture.anyOf(bad, good);

        bad.completeExceptionally(
            new IllegalArgumentException("bad response"));
        good.complete(42);

        try {
            winner.join();
        } catch (CompletionException ex) {
            System.out.println("winner failure = "
                + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("winner exceptional = "
            + winner.isCompletedExceptionally());
        System.out.println("other result = " + good.join());
    }
}
~~~

Compile/run:

~~~bash
javac AnyOfFailureDemo.java
java AnyOfFailureDemo
~~~

Stdout:

~~~text
winner failure = IllegalArgumentException
winner exceptional = true
other result = 42
~~~

The good result `42` **does not overwrite the outcome** of the already-failed `winner`. Therefore, if you need "the fastest **successful** result among multiple fallback sources," plain `anyOf` is **not enough**.

### 8.1. First-Completion vs. First-Success vs. First-Acceptable

| Policy | When one task fails while others are still running | Approach |
| --- | --- | --- |
| First-completion | Terminates immediately with the first outcome, even if FAILED | `anyOf` |
| First-success | Terminates successfully only when a task succeeds; fails only if all tasks fail | Needs a coordinator combining outcomes and counting failures |
| First-acceptable | Can ignore a successful result that fails validation; keeps waiting | Coordinator with validation/timeout |
| All-success-required | One error fails the whole request per contract, even if others succeed | `allOf` with an error policy |
| All-settled | Waits for all, returns a list of each task's status | `handle` each task, then `allOf` |

Do not just use `anyOf(futures).exceptionally(error -> fallback)` and claim you have "first success": that callback can run right after the first error **before** another Future completes successfully.

### 8.2. How to Design First-Success Properly at the Protocol Level

A coordinator can attach a `whenComplete` callback to each Future:

1. When a Future completes **successfully**, attempt `winner.complete(value)`. Only the first callback to complete it succeeds in setting the target Future.
2. When a Future fails, increment a failure counter; **only when all** have failed should you call `completeExceptionally` on the target Future (and you must handle races between success and failure).
3. Record cancellation, timeouts, and "invalid result" conditions according to an explicit policy.
4. If all sources fail, store/aggregate enough causes for debugging instead of reporting a random single error.

This pattern must synchronize **result counting** and "whether a success has already arrived" so you do not declare failure just as a success arrives. You can use `AtomicInteger` for failure counting and `CompletableFuture.complete(...)` for single-winner semantics, but you must reason carefully about completion paths, memory visibility, and callback ordering.

### 8.3. Example 6 — First-Success with Both Failures and Successes (Java 17+)

A simple implementation uses a coordinator that counts failures and picks the first success. With three tasks that may complete in different orders, the following coordinator ensures we do not give up just because the first task fails.

Create file `FirstSuccessDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class FirstSuccessDemo {
    static <T> CompletableFuture<T> firstSuccess(
            CompletableFuture<T>... inputs) {
        if (inputs.length == 0) {
            throw new IllegalArgumentException("inputs empty");
        }

        CompletableFuture<T> result = new CompletableFuture<>();
        AtomicInteger failures = new AtomicInteger();

        for (CompletableFuture<T> input : inputs) {
            input.whenComplete((value, error) -> {
                if (error == null) {
                    result.complete(value);
                } else if (failures.incrementAndGet()
                        == inputs.length) {
                    result.completeExceptionally(error);
                }
            });
        }
        return result;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> first = new CompletableFuture<>();
        CompletableFuture<Integer> second = new CompletableFuture<>();
        CompletableFuture<Integer> third = new CompletableFuture<>();

        CompletableFuture<Integer> best =
            firstSuccess(first, second, third);

        first.completeExceptionally(
            new IllegalArgumentException("first failed"));
        second.complete(99);
        third.complete(77);

        System.out.println("first success = " + best.join());
        System.out.println("third = " + third.join());
        System.out.println("first failed = "
            + first.isCompletedExceptionally());
    }
}
~~~

Compile/run:

~~~bash
javac FirstSuccessDemo.java
java FirstSuccessDemo
~~~

Stdout:

~~~text
first success = 99
third = 77
first failed = true
~~~

**Why does this work in the example?** `first` fails first; the coordinator increments the failure count without terminating. `second` succeeds next, completing `best` with 99. `third` arriving later does not alter the already-completed `best`.

**Limitations:** This is a **minimal illustrative pattern**, not a full-featured race library. It picks one `Throwable` when all fail, does not aggregate errors, and has no protocol for cancelling remaining inputs, timeouts, or null/validation policies. When multiple callbacks actually run concurrently, `CompletableFuture.complete` ensures only one completion wins; the failure counter with "only when all inputs fail" still guarantees not returning failure if an input succeeds, provided every input completes only once and callbacks do not throw before updating. A **first-success** policy is an additional requirement, not a built-in feature of `anyOf`.

## 9. Zero Inputs, Null Inputs, and Varargs Arrays

### 9.1. When There Are No Input Futures

Per the contract:

- `CompletableFuture.allOf()` with **no arguments** returns a Future **already completed normally** with `null`: there is nothing to wait for.
- `CompletableFuture.anyOf()` with **no arguments** returns an **incomplete** Future: no input can ever win.

This is an important edge case. If business logic requires "at least one data source," validate the list **before** calling `anyOf`; otherwise a caller calling `join()` may wait forever on a Future that no one will ever complete.

### 9.2. Example 7 — Empty Arrays (Java 17+)

Create file `EmptyAggregatesDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class EmptyAggregatesDemo {
    public static void main(String[] args) {
        CompletableFuture<Void> allEmpty =
            CompletableFuture.allOf();
        CompletableFuture<Object> anyEmpty =
            CompletableFuture.anyOf();

        System.out.println("all empty done = "
            + allEmpty.isDone());
        System.out.println("all empty null = "
            + (allEmpty.join() == null));
        System.out.println("any empty done = "
            + anyEmpty.isDone());
    }
}
~~~

Compile/run:

~~~bash
javac EmptyAggregatesDemo.java
java EmptyAggregatesDemo
~~~

Stdout:

~~~text
all empty done = true
all empty null = true
any empty done = false
~~~

**Do not call `anyEmpty.join()` in the example**, because there is no input Future or producer to complete it.

### 9.3. Null Inputs

Do not pass `null` as an input Future:

~~~java
// WRONG: null element is invalid.
CompletableFuture.allOf(
    CompletableFuture.completedFuture("ok"), null);
~~~

This throws `NullPointerException` per the contract. A task succeeding with a `null` value is different from the **Future object itself being null**. Distinguish `CompletableFuture.completedFuture(null)` (a valid Future) from `(CompletableFuture<?>) null` (not a Future).

A `List<CompletableFuture<T>>` is commonly converted to an array:

~~~java
// Java 17+ snippet, not a standalone program.
CompletableFuture<?>[] array =
    futures.toArray(new CompletableFuture<?>[0]);
CompletableFuture<Void> all = CompletableFuture.allOf(array);
~~~

Verify that `futures` is non-null, its elements are non-null, and the list is not being concurrently modified by another thread. If the list is mutable and has writers, take a stable snapshot before creating the aggregation.

## 10. Cancellation: Cancelling the Aggregate Does Not Cancel Inputs

This is a design mistake with major practical impact. `CompletableFuture.allOf(...)` and `anyOf(...)` create **dependent Futures**, not a cancellation scope managing the lifecycle of all tasks.

If you call:

~~~java
// Java 17+ snippet, not standalone.
CompletableFuture<Void> all =
    CompletableFuture.allOf(a, b, c);
all.cancel(true);
~~~

There is no guarantee that `a`, `b`, and `c` will be cancelled or interrupted. Usually only the **aggregate Future** transitions to the cancelled state. The inputs may keep running, consuming resources, or completing normally.

Similarly, if `anyOf(a, b, c)` receives a winner and completes, the losers do not stop automatically. If the business requirement is "cancel the remaining requests once one wins," you must perform the appropriate cancellation actions and handle the reality that already-dispatched external tasks may still be running.

### 10.1. Example 8 — Cancelling Aggregate Does Not Cascade (Java 17+)

Create file `CancelAggregateDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class CancelAggregateDemo {
    public static void main(String[] args) {
        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();

        CompletableFuture<Void> combined =
            CompletableFuture.allOf(a, b);

        combined.cancel(true);

        System.out.println("combined cancelled = "
            + combined.isCancelled());
        System.out.println("a cancelled = " + a.isCancelled());
        System.out.println("b cancelled = " + b.isCancelled());

        a.complete("A");
        b.complete("B");

        System.out.println("a result = " + a.join());
        System.out.println("b result = " + b.join());
        System.out.println("combined still cancelled = "
            + combined.isCancelled());
    }
}
~~~

Compile/run:

~~~bash
javac CancelAggregateDemo.java
java CancelAggregateDemo
~~~

Stdout:

~~~text
combined cancelled = true
a cancelled = false
b cancelled = false
a result = A
b result = B
combined still cancelled = true
~~~

The example uses Futures with no attached workers to isolate **aggregate state** from input cancellation. Calling `cancel(true)` on the aggregate does not automatically call `a.cancel(true)` or `b.cancel(true)`.

**Important:** `CompletableFuture.cancel(true)` does not use `mayInterruptIfRunning` to control execution per this class's contract. Do not infer from passing `true` that an underlying task or HTTP call has stopped. Actual cancellation of I/O tasks usually requires an API that supports cancellation, timeouts, or closing resources.

### 10.2. Does a Cancelled Input Make the Aggregate isCancelled()?

An input that is `cancel(...)`-ed typically completes exceptionally, and the dependent aggregate can complete exceptionally per the contract. **Do not assume `allOf.isCancelled()` or `anyOf.isCancelled()` is necessarily true** when an input is cancelled: the cancellation state of the **aggregate object** is distinct from it completing exceptionally due to a `CancellationException` from an input.

To report cancellation accurately, inspect each input if needed, while distinguishing the root `CancellationException`, a wrapping `CompletionException`, and the aggregate's own state.

## 11. Timeouts and Deadlines When Waiting on Multiple Tasks

### 11.1. What Does a Timeout Actually Limit?

Common APIs:

- `all.get(timeout, unit)`: limits **the caller's wait time**; on expiration it can throw `TimeoutException`, and **does not automatically cancel** `all` or the inputs.
- `all.orTimeout(timeout, unit)`: in Java 9+, establishes an exceptional completion path with `TimeoutException` if **that** Future has not completed on time. It returns **the same CompletableFuture it was called on**, not a completely independent Future.
- `all.completeOnTimeout(value, timeout, unit)`: sets a completion value if the Future has not completed after the deadline; for `allOf` of type `Void`, the appropriate value is usually `null`, though that decision can easily mask a "not all tasks finished" error.
- `any.orTimeout(...)`: applies the timeout to `any` itself; it does not stop the inputs.

**A timeout on the aggregate does not mean the underlying tasks have been cancelled.** If the caller gives up at the deadline, the underlying tasks may still occupy workers/connections and produce side effects.

### 11.2. Deadline Pattern with Explicit Cancellation

~~~java
// Java 17+ snippet, not a standalone program.
CompletableFuture<Void> all =
    CompletableFuture.allOf(a, b, c);

try {
    all.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    a.cancel(true);
    b.cancel(true);
    c.cancel(true);
    // Report timeout; verify cleanup of external operations if needed.
}
~~~

You must handle or propagate `InterruptedException` and `ExecutionException` at the caller. Cancelling these `CompletableFuture` instances usually only changes their state; **to stop real I/O**, integrate with the underlying operation's cancellation API.

Do not write business logic assuming "we cancelled everything so no more callbacks will arrive." Cancellation and external completion can race; a late cancellation request may not prevent downstream code from having already processed data.

### 11.3. Timeout vs. Execution Error

If `anyOf` receives an early failing Future, it completes exceptionally even if other tasks have not reached the deadline. If you want first-success-until-deadline, you need a coordinator that does not terminate on early errors, attaches its own deadline, and tracks the remaining in-flight sources.

## 12. Avoiding Deadlocks, Starvation, and Misplaced Blocking

### 12.1. Do Not Join a Future Whose Task Has Not Been Run by the Executor

A dangerous design example:

~~~java
// WRONG if both tasks run on the same single-thread executor.
ExecutorService pool = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> outer =
    CompletableFuture.supplyAsync(() -> {
        CompletableFuture<Integer> inner =
            CompletableFuture.supplyAsync(() -> 42, pool);
        return inner.join(); // Blocks the pool's only worker.
    }, pool);
~~~

`outer` occupies the only worker, submits `inner` to the queue, and waits for `inner`. But `inner` cannot run because the worker is held by `outer`. This is a **task-level dependency stall/deadlock**, even without classic monitor locks.

The fix is usually **non-blocking** composition using `thenCompose`, `thenCombine`, or submitting independent tasks from outside the worker and attaching continuations; if blocking is unavoidable, analyze capacity/queues and dependencies before choosing an executor.

### 12.2. thenApply vs. thenApplyAsync

- `thenApply(fn)` may run on the thread that completed the upstream stage or on the thread registering the callback if the stage is already complete, depending on the situation.
- `thenApplyAsync(fn)` submits the continuation to the default executor; the overload taking an executor lets you control where it runs.
- Do not assume every continuation runs on main or on a separate worker.

If `allOf`'s continuation does heavy work, consider `thenApplyAsync(..., dedicatedExecutor)` as appropriate. If it only collects results from already-succeeded Futures, `thenApply` is usually simpler and avoids scheduling overhead.

### 12.3. Do Not Join Every Future on the Same Pool Before Submitting Them

To preserve concurrency, start all independent work first and then compose the Futures. When there is a true dependency order (e.g., B needs A's result), use `thenCompose` to express the dependency rather than blocking a worker with `join` waiting for the next task.

`CompletableFuture` helps **express a dependency graph**, but it does not stop you from building a dependency graph with a waiting cycle.

## 13. Error Management and Centralized Logging

### 13.1. Observing Each Input's Outcome

A FAILED `allOf` aggregate may only surface a single cause, whereas monitoring usually needs to know **which source failed**. Attach an ID:

~~~java
// Java 17+ snippet, not a standalone program.
record Result<T>(String source, T value, Throwable failure) {}

CompletableFuture<Result<String>> profileResult =
    profile.handle((value, err) ->
        new Result<>("profile", value, err));

CompletableFuture<Result<String>> settingsResult =
    settings.handle((value, err) ->
        new Result<>("settings", value, err));
~~~

You can call `allOf` on the `Result` Futures and collect the list after completion. When a source fails, log the exception with its source name/context rather than just logging "CompletionException" without knowing which task failed.

### 13.2. Watch Out for Nested CompletionExceptions

`CompletionException` can wrap an `IllegalArgumentException` or a domain error; multiple stages can add wrapping layers. When putting errors into logs or HTTP responses, unwrap the cause appropriately without losing stack traces or context.

Do not blindly "unwrap all the way to the root" if intermediate wrappers carry business meaning. For example, `CancellationException`, `TimeoutException`, or resource-error exceptions may need distinct policies.

### 13.3. allOf Does Not Provide Transactions

If three tasks perform three irreversible updates, `allOf` only **waits for outcomes**; it does not roll back when one task fails. If you need an atomic business operation, design transactions, idempotency, compensation, or an outbox/ack protocol separately.

With `anyOf` racing multiple fallback sources, a **loser** may also have completed its side effect before you attempt to cancel it; only use such a race for tasks that are safe to run redundantly or have deduplication mechanisms.

## 14. Understanding Cancellation and Interruption in CompletableFuture

Some common misconceptions:

1. Calling `cf.cancel(true)` on a `CompletableFuture` does not promise to interrupt the thread running the `Supplier`. Per the contract, `mayInterruptIfRunning` is not used to control execution in this class.
2. When an `allOf`/`anyOf` aggregate is cancelled, inputs are not automatically cancelled. Each input can keep running.
3. When an input Future is cancelled, a dependent stage can complete exceptionally with a `CompletionException` wrapping `CancellationException`, rather than the aggregate itself necessarily reporting `isCancelled() == true`.
4. A cancelled `Future` does not prove files were closed, connections were released, or third-party systems rolled back.
5. `anyOf` winning does not automatically cancel losers; cancelling losers also does not guarantee stopping side effects that have already begun.

If you need a **structured lifetime** for multiple subtasks, do not expect `allOf/anyOf` to provide it out of the box. You must define scope ownership, deadlines, cancellation, resources, and completion confirmation points.

### 14.1. When Should You Cancel Losers?

When multiple tasks fetch **the same replaceable data**, cancelling losers can save resources, but only when:

- Each task has an actually effective cancellation mechanism.
- Side effects are idempotent or constrained.
- Late results do not overwrite the winner.
- Cleanup does not leak connections, permits, or buffers.
- The caller is not left holding a seemingly cancelled Future while an actual worker silently keeps running.

If tasks write critical data, "whoever finishes first" may not be the right strategy; do not use a race to drive business state before clarifying consistency guarantees.

## 15. Edge Cases and Contracts to Memorize

| Scenario | `allOf` | `anyOf` |
| --- | --- | --- |
| No inputs | Completes normally with `null` immediately | Returns an incomplete Future |
| One input, success | Follows input; completes normally with `null` | Returns the input's value |
| One input, failure | Exceptional completion | Exceptional completion |
| N inputs, all succeed | Completes when all have succeeded | Completes when the first input succeeds |
| N inputs, one early failure | Eventually exceptional completion; does not auto-cancel remaining inputs | Early failure can win immediately |
| N inputs, one input cancelled | Aggregate may complete exceptionally; not necessarily `isCancelled()` itself | Cancellation can be the exceptional winner |
| Input has result `null` | Aggregate success is still `null` | Winner can succeed with `null` |
| Multiple Futures complete nearly simultaneously | Does not produce a result list | Winner depends on completion race; no order guaranteed |
| Calling cancel on aggregate | Does not automatically cancel inputs | Does not automatically cancel inputs |
| Caller timeout while waiting | Does not automatically cancel inputs | Does not automatically cancel inputs |

**Reminder:** `anyOf` does not prioritize "the input placed earlier in the array." When two Futures actually race, the winner is decided by completion timing, not because a Future was passed at array index 0.

## 16. Practice Exercises

### Exercise A: Three Independent Sources

Write three `CompletableFuture<String>` tasks loading data A, B, C on a fixed executor. Use `allOf` and `thenApply` to return `List<String>` in order A, B, C. Include a `CountDownLatch` in a test to prove all three tasks started before results are processed.

**Correctness criteria:** do not call `join()` immediately after creating each Future; do not treat `all.join()` as a `List`; shut down the executor.

### Exercise B: One Source Fails

Change B to a task throwing `IllegalArgumentException`. Distinguish `all.join()` throwing `CompletionException` from `B.join()` throwing the corresponding error. Use `handle` to collect a report containing A SUCCESS, B FAILED, and C SUCCESS.

**Correctness criteria:** do not lose good results; do not turn errors into fake successes if business logic needs failure reporting.

### Exercise C: First-Completion vs. First-Success

Create two Futures where one task fails first and the other succeeds later. Compare the results of `anyOf` and the `firstSuccess` coordinator from the earlier section.

**Correctness criteria:** `anyOf` fails according to the first to complete; `firstSuccess` still receives the later task's success value.

### Exercise D: Timeout Does Not Auto-Cancel

Use an incomplete `CompletableFuture` and call `get(100, TimeUnit.MILLISECONDS)` to observe `TimeoutException`. Verify that the Future can still be `complete("late")`-ed after the timeout.

**Correctness criteria:** waiting with a timeout does not automatically cancel the Future. Set reasonable test timeouts to avoid long waits, without relying on exact scheduler precision.

### Exercise E: Cancelling an Aggregate

Create two incomplete Futures, combine them with `allOf`, and call `all.cancel(true)`. Check the state of each input before and after they are individually completed; compare with `CancelAggregateDemo`.

**Correctness criteria:** do not infer that inputs were cancelled/interrupted due to cancelling the aggregate.

## 17. Testing Concurrency: Do Not Guess Scheduling

### 17.1. Common Testing Mistakes

~~~java
// WRONG for deterministic testing intent.
// Not a standalone program.
CompletableFuture<String> a =
    CompletableFuture.supplyAsync(() -> slowCall());
CompletableFuture<String> b =
    CompletableFuture.supplyAsync(() -> fastCall());

Thread.sleep(50);
assertEquals("fast", CompletableFuture.anyOf(a, b).join());
~~~

There is no guarantee `fastCall` finishes before `slowCall` just because of method names or how long main sleeps. On a busy CI machine, DNS/network/JIT/scheduler behavior can differ. If you need to test **semantics**, use manual `complete` on incomplete Futures or latches to control ordering.

### 17.2. Required Test Cases

- `allOf` all succeed: composite Future is `Void`, values are in each input.
- `allOf` one task fails: error is reflected, good tasks retain their outcomes.
- `anyOf` success first: winner gets the right value, losers keep running/completing.
- `anyOf` failure first: aggregate fails, even though remaining tasks may succeed later.
- `anyOf` different input types: no unchecked `Object` casts.
- Empty array: `allOf` is done, `anyOf` is not done; do not join an empty `anyOf`.
- `null` Future element: factory rejects it.
- Task validly returning `null`: not confused with a null Future.
- Cancel aggregate: inputs are not cancelled by default.
- Input cancelled: distinguish aggregate exceptional completion from `isCancelled()`.
- Timeout: caller timeout does not automatically stop inputs.
- `InterruptedException` from `get()`: propagate or restore interrupt flag per contract.
- Executor with too few workers: detect dependency stalls, do not let tests hang indefinitely.
- Shutdown: no leaked workers or callbacks holding resources too long.

### 17.3. Measuring Performance Properly

Every measurement should distinguish:

1. **Submission latency**: how long it takes to submit the tasks.
2. **Per-task execution latency**: actual CPU/I/O time.
3. **Aggregation latency**: until all results are ready or the winner arrives.
4. **Cancellation/cleanup latency**: how long after cancellation resources are actually released.
5. **Tail latency**: p95/p99—in particular, `allOf` is often dominated by the slowest task in the group.

Do not take a few `System.currentTimeMillis()` measurements and conclude `anyOf` is always better than `allOf`. The two methods solve **two different business semantics** and cannot be compared simply as equivalent implementations.

## 18. Pre-Production Checklist for allOf/anyOf

- Are the tasks **independent** and able to run concurrently, or is there a required dependency order?
- Do you need **all**, **first completed**, **first successful**, or **first validated result**?
- Have you chosen an executor suited for CPU-bound vs. blocking I/O work?
- Are queue bounds, worker counts, in-flight requests, and shared resources bounded?
- Have you avoided calling `join()` on subtasks on the same executor whose workers are already occupied?
- With `allOf`, are you collecting values from each typed Future instead of casting `Void`?
- If an input can return null, does the aggregated list use a data structure that allows null?
- When a task fails, have you decided whether to fail the entire request or preserve partial results?
- Are you collecting errors by source ID rather than just a single exception from the aggregate?
- With `anyOf`, do you understand that the first error is also a winner?
- Have you avoided unchecked `Object` casts from mixed-type `anyOf`?
- Have you validated that the input list is non-empty before calling `anyOf`?
- Have you avoided passing a null Future in varargs?
- Is there a request deadline and a realistic timeout policy?
- Is it clear **who** is responsible for cancelling losers/inputs and performing cleanup?
- Have you avoided treating `CompletableFuture.cancel(true)` as proof that the worker was interrupted?
- Are outcomes tested with latches and manual completion rather than sleeps guessing the scheduler?
- Do you shut down executors with a deadline and handle still-running tasks?
- Have you verified that side effects occurring after timeout/cancellation are handled with proper idempotency?

## 19. Self-Check Questions

**1.** Does `CompletableFuture.allOf(a, b).join()` return a list of results from `a` and `b`?

No. `allOf` returns `CompletableFuture<Void>`; on success, `join()` returns `null`. Use `a.join()` and `b.join()` to get each Future's value after `allOf` succeeds.

**2.** Does `anyOf(a, b)` guarantee the first successful task?

No. It completes with the **outcome of the first task to complete**; that task may fail. First-success requires a separate coordinator.

**3.** If one task fails, does `allOf` automatically cancel the remaining tasks?

No. Inputs can keep running and producing side effects. A separate cancellation protocol is needed when required.

**4.** Once `anyOf` returns a winner, do the losing tasks stop automatically?

No. The composite result finishing does not automatically cancel or interrupt the losers.

**5.** Why does `anyOf` return `CompletableFuture<Object>`?

Because inputs can have different types and the compiler cannot know which input will win. Even if all inputs have the same type, you need a checked cast or a wrapper record.

**6.** How do `allOf()` and `anyOf()` with no arguments differ?

`allOf()` returns a Future already succeeded with `null`; `anyOf()` returns an incomplete Future with no winner. Do not call `join()` on an empty `anyOf` without additional logic.

**7.** Does `get(timeout)` throwing `TimeoutException` mean the tasks were cancelled?

No. That is only the **caller's wait** timing out. The Futures can continue and complete later.

**8.** A task in a 1-thread pool creates a subtask on the same pool and calls `join()` on it. What is the risk?

The subtask has no free worker to run on while the parent task blocks waiting; this can cause a deadlock/dependency stall. Use non-blocking composition and design appropriate capacity.

**9.** Does `allOf` guarantee results in completion order?

No. The order in which you collect values (e.g., `List.of(a.join(), b.join())`) is defined by you, not by the order tasks finish.

**10.** Why can `allOf` fail while some inputs are still SUCCESS?

Because each Future has its own outcome. The aggregate can be FAILED if any input fails, even if other inputs completed normally.

**11.** Does cancelling `CompletableFuture.allOf(a, b)` guarantee that `a.isCancelled()` and `b.isCancelled()` become true?

No. Aggregate cancellation does not necessarily cascade down to inputs.

**12.** If task A completes normally with `null` while task B is still running, can `anyOf(A, B)` succeed with `null`?

Yes. `null` is a **valid result value** for A, not a signal that it is "still incomplete."

## 20. JDK References and Summary

Contracts to cross-check in the Javadoc for your JDK version:

- [CompletableFuture — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [CompletionStage — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [ExecutorService — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

**Cheat sheet:**

~~~text
allOf(a, b, c):
  Waits for all Futures to complete.
  If all succeed -> CompletableFuture<Void> success(null).
  If one or more fail -> aggregate exceptional completion.
  Values reside in each typed input Future.

anyOf(a, b, c):
  Takes the first completed outcome: success OR failure.
  Returns CompletableFuture<Object>.
  Not first-success by default; does not cancel losers.

Both:
  Do not run tasks, create threads, or set timeouts on their own.
  Do not automatically cancel inputs when the aggregate completes/cancels.
  Not transactions; do not automatically clean up side effects.
~~~

**Conclusion:** Choose `allOf` when work requires **all results**, and use `anyOf` when you want the **first completed outcome** and accept that a failure may win. For more complex requirements such as first-success, partial successes, deadlines, or cancelling losers, design an explicit protocol rather than attributing guarantees to these two factory methods that they do not have.