# completedStage(), failedFuture(), failedStage(): Already Available Results and Error Results

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain **CompletionStage<T>** and **CompletableFuture<T>** in Java concurrency; distinguish **normal completion**, **exceptional completion**, and the incomplete (pending) state.
- Understand the three factories **CompletableFuture.completedStage(value)**, **CompletableFuture.failedFuture(exception)**, **CompletableFuture.failedStage(exception)** and compare them with **completedFuture(value)**.
- Know why completedStage/failedStage have the minimal **CompletionStage<U>** public return type, whereas failedFuture/completedFuture have the full **CompletableFuture<U>** public return type.
- Design APIs that have an immediate result or input error while still returning a unified asynchronous-style contract.
- Distinguish **thenApply**, **thenCompose**, **thenApplyAsync**, **exceptionally**, **exceptionallyCompose**, **handle**, and **whenComplete** on a normal upstream and an already-failed upstream.
- Retrieve results/errors properly via **toCompletableFuture()**, **join()**, and **get()**, and understand **CompletionException** and **ExecutionException**.
- Identify misconceptions about **thread scheduling**, **cancellation**, **mutable results**, **null**, immediate callback execution, masked errors, and imaginary retries.
- Compile and run Java 17+ programs with deterministic stdout, without relying on Thread.sleep or random scheduling order.

This lesson belongs to **Java Advance - concurrency**, under the **CompletableFuture** group, and only covers general Java concurrency utilities. Spring-related topics have their own dedicated chapter.

## 2. Two Foundational Interfaces: CompletionStage and Future

**CompletionStage<T>** represents a stage of a computation pipeline. It allows registering work that depends on the completion of a previous stage, enabling composition into an entire graph of steps.

**Future<T>** provides a mechanism to observe a result that may arrive in the future: **get()**, completion status, and cancellation.

**CompletableFuture<T>** implements both **CompletionStage<T>** and **Future<T>**, and also provides methods to complete the result such as **complete()** and **completeExceptionally()**.

~~~text
CompletionStage<T>          Future<T>
  | thenApply                | get()
  | thenCompose              | cancel()
  | exceptionally            | isDone()
  | handle                   |
  +-----------+--------------+
              |
       CompletableFuture<T>
              |
        complete / join
        completeExceptionally
        isCompletedExceptionally
~~~

In public methods, choosing the return type is a design decision:

- Return **CompletionStage<T>** if the caller only needs composition—that is, chaining, combining, or recovery.
- Return **CompletableFuture<T>** if the caller genuinely needs a concrete Future with get/join/cancel, or if the contract allows controlling completion.
- Do not assume a **CompletionStage** object can be safely cast to CompletableFuture and have any method called on it. A minimal stage may not support operations outside the interface.

### Three Important States

1. **Pending:** no final result yet; a task may be executing or not yet scheduled.
2. **Normal completion:** completed with a value, including **null**.
3. **Exceptional completion:** completed exceptionally with a Throwable; downstream only succeeds if there is recovery.

**A failed Future is also a done Future.** isDone() does not answer the question "has the business operation succeeded or not".

## 3. Factories for Already Known Results

| Factory | Public return type | State immediately upon return | Creates task/thread? |
| --- | --- | --- | --- |
| **completedFuture(value)** | CompletableFuture<U> | Normal completion | No |
| **completedStage(value)** | CompletionStage<U> | Normal completion | No |
| **failedFuture(ex)** | CompletableFuture<U> | Exceptional completion | No |
| **failedStage(ex)** | CompletionStage<U> | Exceptional completion | No |

**completedFuture** has been available since Java 8. **completedStage**, **failedFuture**, and **failedStage** were added in Java 9. Java 17 supports all four.

These are **static factory methods** of the CompletableFuture class, not constructors that start a worker. Creating a completed/failed stage itself represents an **already-existing final state**.

### Do Not Confuse Result with Execution

A method may return CompletionStage because callers are used to an asynchronous model, yet on a **cache hit** or **invalid input** path, the result is already known at call time. There is no mandatory reason to create a Thread or a fake supplyAsync just to maintain the return type.

~~~java
// Snippet inside a method returning CompletionStage<String>.
if (cached != null) {
    return CompletableFuture.completedStage(cached);
}
if (!valid) {
    return CompletableFuture.failedStage(
            new IllegalArgumentException("invalid input")
    );
}
return loadAsync();
~~~

The variables and loadAsync are hypothetical components. The snippet is not standalone runnable code. It expresses a unified API: both the normal path and the error path can have continuations attached by the caller.

## 4. completedStage(value): Success and Granting Composition Only

**CompletableFuture.completedStage(value)** returns a CompletionStage<U> that has already completed normally.

~~~java
CompletionStage<String> s =
        CompletableFuture.completedStage("ready");

CompletionStage<String> upper =
        s.thenApply(String::toUpperCase);
~~~

No executor is required. Because the upstream is already complete, the thenApply callback **may run immediately on the thread registering the continuation**. Do not infer that every callback runs on a different thread.

### completedStage Is Not Synonymous with completedFuture

Both have the same **normal result** given the same value, but differ in **API surface**.

- completedStage: only promises **CompletionStage**, suitable for exposing a pipeline without granting direct complete/cancel permissions.
- completedFuture: returns a **full CompletableFuture**, convenient if the caller needs join/get/isDone/cancel.
- The caller can call **CompletionStage.toCompletableFuture()** to obtain a CompletableFuture for interop; with a minimal stage, the result may be **a different CompletableFuture object**.
- Do not cast to the runtime implementation of a minimal stage, because methods outside CompletionStage may be unsupported and throw UnsupportedOperationException.

### Null Is a Valid Value on Success

**completedStage(null)** and **completedFuture(null)** represent normal completion with a null value. This is completely different from **failedStage(ex)**. If downstream calls value.toString() when value is null, the callback itself will produce a new error.

Consider using **Optional<T>** or an explicit domain result if you do not want null to become a hard-to-control valid state.

## 5. Example 1: completedStage and completedFuture

File **CompletedStageDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CompletedStageDemo {
    public static void main(String[] args) {
        CompletionStage<String> stage =
                CompletableFuture.completedStage("ready");
        CompletableFuture<String> future =
                CompletableFuture.completedFuture("ready");

        CompletionStage<String> upper =
                stage.thenApply(String::toUpperCase);

        CompletionStage<String> nullable =
                CompletableFuture.completedStage(null);

        System.out.println("stage = "
                + upper.toCompletableFuture().join());
        System.out.println("future = " + future.join());
        System.out.println("null normal = "
                + (nullable.toCompletableFuture().join() == null));
        System.out.println("done = " + future.isDone());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompletedStageDemo.java
java CompletedStageDemo
~~~

Stdout:

~~~text
stage = READY
future = ready
null normal = true
done = true
~~~

**Explanation:**

1. Both stage and future are complete before main registers continuations.
2. thenApply transforms the value "ready" into "READY".
3. toCompletableFuture().join() allows retrieving the result from a CompletionStage.
4. Normal completion can have a null value; the null comparison expression returns true.
5. isDone() is true here because completedFuture has completed normally.

Do not use this example to prove that a non-Async callback always runs inline. The API allows several execution context choices; to guarantee a specific executor, specify it on the Async overload.

## 6. failedFuture(Throwable): An Already-Failed Full Future

**CompletableFuture.failedFuture(ex)** creates a CompletableFuture<U> that has already **completed exceptionally** with the provided Throwable ex. It **does not throw ex itself to the caller when creating the factory**.

~~~java
CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("not available")
        );
~~~

Notable states:

| Query or operation | Result when failedFuture(IllegalStateException) |
| --- | --- |
| **isDone()** | true |
| **isCompletedExceptionally()** | true |
| **isCancelled()** | false |
| **get()** | throws ExecutionException containing the root cause |
| **join()** | throws CompletionException containing the root cause |
| **thenApply(fn)** | does not call fn; dependent stage is also exceptional |
| **exceptionally(fn)** | calls fn to produce a recovery value |

**An already-existing error** differs from a task that has not finished yet and throws an error later. A failed Future has no background job created by the failedFuture factory itself.

### An Exception in the Factory Does Not Mean Throwing Directly

~~~java
CompletableFuture<String> result =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad request")
        );
~~~

The method still **returns result**. To observe the exception, the caller uses get/join/exceptionally/handle. This differs from code that executes **throw new IllegalArgumentException(...)**, which exits the method via the normal stack flow.

Representing errors via exceptional completion is especially useful if the API promises to **always return a Future/Stage** for both validation failures and errors that complete later.

## 7. Example 2: Observing Errors via get and join

File **FailedFutureGetJoinDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class FailedFutureGetJoinDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("failed")
                );

        System.out.println("done = " + failed.isDone());
        System.out.println("exceptional = "
                + failed.isCompletedExceptionally());
        System.out.println("cancelled = " + failed.isCancelled());

        try {
            failed.get();
        } catch (ExecutionException ex) {
            System.out.println("get wrapper = "
                    + ex.getClass().getSimpleName());
            System.out.println("get cause = "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println("join wrapper = "
                    + ex.getClass().getSimpleName());
            System.out.println("join cause = "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FailedFutureGetJoinDemo.java
java FailedFutureGetJoinDemo
~~~

Stdout:

~~~text
done = true
exceptional = true
cancelled = false
get wrapper = ExecutionException
get cause = IllegalStateException
join wrapper = CompletionException
join cause = IllegalStateException
~~~

**Note on wrappers:** in this example, the ex provided directly is IllegalStateException, so get() and join() use the wrappers above. In complex pipelines, there may already be a CompletionException from a previous step; do not write logic assuming every error always has exactly one wrapping layer.

**Future.get()** also has a checked InterruptedException when the caller is interrupted; the get(timeout, unit) overload can throw TimeoutException if not yet done. However, failedFuture is already done immediately, so this code does not wait on a worker.

## 8. failedStage(Throwable): An Already-Existing Error as a CompletionStage

**CompletableFuture.failedStage(ex)** returns a CompletionStage<U> that has completed exceptionally.

~~~java
CompletionStage<String> stage =
        CompletableFuture.failedStage(
                new IllegalArgumentException("invalid")
        );
~~~

Characteristics:

- Only the public **CompletionStage API** is promised.
- **thenApply** and **thenCompose** do not run the success lambda because there is no successful result.
- **exceptionally** can produce a fallback.
- **handle** can inspect both result and error.
- **whenComplete** can observe the error, but does not by default turn the stage into normal.
- **toCompletableFuture()** converts to a full CompletableFuture so the caller can call get/join if needed.
- Do not arbitrarily cast the stage to CompletableFuture and call complete/cancel/join on a minimal implementation, as methods not belonging to CompletionStage may be unsupported.

**Why do we need a minimal stage?** It is a way to reduce completion-control privileges through the public API. This is useful when a method only wants to grant **composition capability** without promising the consumer the right to mutate internal promise state.

### When Choosing Between the Two Failed Factories

- Method declares **CompletableFuture<T>**: choose **failedFuture(ex)** if an error is already present.
- Method declares **CompletionStage<T>**: **failedStage(ex)** clearly expresses composition-only intent.
- They do not differ in "error severity" or "when the exception occurred": both are already exceptional before returning.

## 9. Success and Error Continuations

| Chaining method | If upstream is normal | If upstream is exceptional |
| --- | --- | --- |
| **thenApply(fn)** | calls fn with value, produces result | skips fn, propagates failure |
| **thenCompose(fn)** | calls fn returning CompletionStage then flattens | skips fn, propagates failure |
| **thenAccept(consumer)** | calls consumer on value | skips consumer |
| **thenRun(runnable)** | calls runnable | skips runnable |
| **exceptionally(fn)** | preserves normal result | calls fn to produce fallback |
| **handle(fn)** | calls fn with null error | calls fn with non-null error |
| **whenComplete(action)** | observes success, normally preserves outcome | observes failure, normally preserves outcome |
| **thenApplyAsync(fn, executor)** | schedules fn via provided executor | does not run success-only fn because upstream failed |

**Do not confuse whenComplete and handle**: whenComplete primarily observes, whereas handle can transform a result/error into a new value. If the callback itself throws an exception, downstream can become exceptional; attaching a handler does not guarantee it will never fail.

An illustrative pipeline:

~~~text
failedStage(IllegalArgumentException)
   |
   +-- thenApply(parse) -----------> parse is not called
   |                                      |
   |                                failed downstream
   |
   +-- exceptionally(fallback) ----> normal result
   |
   +-- handle(result, error) ------> callback returns result based on error
   |
   +-- whenComplete(log) ----------> log is called, error does not auto-recover
~~~

**exceptionally receives a Throwable**, which may be a wrapper depending on how the previous step completed. Do not unconditionally cast it to a domain exception without checking the type and cause.

## 10. Example 3: thenApply Skipped and exceptionally Recovery

File **FailedStageRecoveryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

public class FailedStageRecoveryDemo {
    public static void main(String[] args) {
        AtomicBoolean mapped = new AtomicBoolean();

        CompletionStage<String> failed =
                CompletableFuture.failedStage(
                        new IllegalArgumentException("bad")
                );

        CompletionStage<String> successOnly =
                failed.thenApply(value -> {
                    mapped.set(true);
                    return value.toUpperCase();
                });

        CompletionStage<String> recovered =
                successOnly.exceptionally(error -> "fallback");

        CompletionStage<String> handled =
                failed.handle((value, error) ->
                        error == null ? value : "handled"
                );

        System.out.println("thenApply called = " + mapped.get());
        System.out.println("recovered = "
                + recovered.toCompletableFuture().join());
        System.out.println("handled = "
                + handled.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FailedStageRecoveryDemo.java
java FailedStageRecoveryDemo
~~~

Stdout:

~~~text
thenApply called = false
recovered = fallback
handled = handled
~~~

In the example, **the upstream failed before thenApply was registered**. There is no successful value, so thenApply is skipped. Then **exceptionally** turns the exceptional completion into the normal result "fallback". **handle** reads the error and returns "handled".

If a callback in exceptionally or handle also throws, the dependent stage itself can fail again. Recovery must be tested, not treated as an automatic guarantee.

## 11. Example 4: whenComplete Is Observation, handle Is Recovery

File **WhenCompleteDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

public class WhenCompleteDemo {
    public static void main(String[] args) {
        AtomicBoolean seenError = new AtomicBoolean();

        CompletionStage<Integer> bad =
                CompletableFuture.failedStage(
                        new IllegalStateException("unavailable")
                );

        CompletionStage<Integer> observed =
                bad.whenComplete((value, error) ->
                        seenError.set(error != null)
                );

        boolean stillFailed = false;
        try {
            observed.toCompletableFuture().join();
        } catch (CompletionException ex) {
            stillFailed = true;
        }

        CompletionStage<Integer> recovered =
                bad.handle((value, error) ->
                        error == null ? value : 42
                );

        System.out.println("error observed = " + seenError.get());
        System.out.println("still failed = " + stillFailed);
        System.out.println("recovered = "
                + recovered.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 WhenCompleteDemo.java
java WhenCompleteDemo
~~~

Stdout:

~~~text
error observed = true
still failed = true
recovered = 42
~~~

**Why is this right?** The whenComplete callback records the error but has no fallback value. The observed branch remains exceptional. Conversely, handle actively returns Integer 42, so the recovered branch is normal.

A telemetry callback should not perform heavy blocking I/O or arbitrarily throw exceptions, as doing so can introduce additional errors into the chain and obscure the original failure.

## 12. thenCompose to Chain an Already-Existing Stage

**thenApply** transforms T into U. **thenCompose** transforms T into CompletionStage<U> and then **flattens** it into CompletionStage<U> for downstream.

~~~java
// Illustrates a pipeline:
CompletionStage<Integer> value =
        CompletableFuture.completedStage(20)
            .thenApply(n -> n + 1)
            .thenCompose(n ->
                    CompletableFuture.completedStage(n * 2)
            );
~~~

The resulting stage holds Integer 42, not a CompletionStage nested inside a CompletionStage. No new thread is needed, because both steps here already have results ready.

### Example 5: Composition Without Creating Fake Tasks

File **StageCompositionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class StageCompositionDemo {
    public static void main(String[] args) {
        CompletionStage<Integer> value =
                CompletableFuture.completedStage(20)
                    .thenApply(n -> n + 1)
                    .thenCompose(n ->
                            CompletableFuture.completedStage(n * 2)
                    );

        System.out.println("value = "
                + value.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StageCompositionDemo.java
java StageCompositionDemo
~~~

Stdout:

~~~text
value = 42
~~~

**Key point:** an async-style API **is allowed to complete synchronously** in cases where the result is already known. Do not create supplyAsync just for appearances.

If downstream needs real I/O, thenCompose can return a stage from an I/O operation. In that case the result may arrive later; the way the chain is written does not need to change.

## 13. Which Thread Does the Callback Run On?

A common misconception: **thenApply** on completedStage always runs on a background worker. In reality, non-Async dependent actions may be executed by the thread that completes the stage, the thread that registers the continuation, or a thread permitted by the runtime under the contract.

Because the upstream is already complete before registration, **thenApply may run immediately on the caller thread**. If the callback is heavy and blocking, the caller can be blocked inside the thenApply call itself.

**thenApplyAsync** requests asynchronous scheduling, which can use CompletableFuture's default async execution facility or an executor passed by the caller.

**Async does not mean creating a new thread:** an executor can reuse worker threads from a pool.

### Example 6: Passing an Explicit Executor

File **ExplicitExecutorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExplicitExecutorDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Thread caller = Thread.currentThread();

        try {
            CompletionStage<Boolean> value =
                    CompletableFuture.completedStage("ready")
                        .thenApplyAsync(
                            text -> Thread.currentThread() != caller,
                            executor
                        );

            System.out.println("different thread = "
                    + value.toCompletableFuture().join());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitExecutorDemo.java
java ExplicitExecutorDemo
~~~

Stdout:

~~~text
different thread = true
~~~

The callback runs on a worker managed by the executor, not main. The example checks **Thread object identity**, without relying on arbitrary thread names.

In real applications, an executor also has **queues, saturation, rejection, shutdown, thread factories**, and resource limits. If the executor cannot accept the callback because it is shut down or overloaded, downstream can fail. Do not confuse a normal upstream completedStage with a guarantee that **every future dependent task will definitely run**.

## 14. Error Factories in Public APIs

Suppose a method must return CompletionStage<Integer> even though the input may be invalid:

~~~java
// Illustrative snippet; the parseAsync method belongs to a class.
CompletionStage<Integer> parseAsync(String input) {
    if (input == null) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("missing input")
        );
    }
    return CompletableFuture.completedStage(
            Integer.parseInt(input)
    );
}
~~~

**This snippet does not handle NumberFormatException** from parseInt: it can throw **directly** before returning a CompletionStage. If the API promises that **all validation errors appear as exceptional completions**, catch the parse error and return failedStage.

### Example 7: Always Returning a Stage for Validation Errors

File **ValidationStageDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ValidationStageDemo {
    static CompletionStage<Integer> parsePositive(String input) {
        if (input == null) {
            return CompletableFuture.failedStage(
                    new IllegalArgumentException("missing")
            );
        }

        try {
            int value = Integer.parseInt(input);
            if (value <= 0) {
                return CompletableFuture.failedStage(
                        new IllegalArgumentException("not positive")
                );
            }
            return CompletableFuture.completedStage(value);
        } catch (NumberFormatException ex) {
            return CompletableFuture.failedStage(ex);
        }
    }

    public static void main(String[] args) {
        CompletionStage<String> valid =
                parsePositive("21")
                    .thenApply(n -> "double=" + (n * 2));

        CompletionStage<String> invalid =
                parsePositive("invalid")
                    .thenApply(n -> "double=" + (n * 2))
                    .exceptionally(error -> "rejected");

        System.out.println(valid.toCompletableFuture().join());
        System.out.println(invalid.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidationStageDemo.java
java ValidationStageDemo
~~~

Stdout:

~~~text
double=42
rejected
~~~

Invalid validation is represented with **failedStage**, sparing the caller from having to catch NumberFormatException around the parsePositive call. The caller can attach **exceptionally** to produce a fallback.

**Do not turn every system error into an input error:** choose appropriate domain exceptions, causes, retries, and user-facing information.

## 15. A Callback Error Can Produce a Failed Downstream

A normal upstream can still produce a failed downstream if the callback throws:

~~~java
CompletionStage<Integer> stage =
        CompletableFuture.completedStage("not a number")
            .thenApply(Integer::parseInt);
~~~

Here the upstream completed normally with a String; **Integer.parseInt** throws NumberFormatException when the callback runs, making the resulting stage exceptional.

Similarly:

~~~java
CompletableFuture.completedStage(null)
        .thenApply(String::length);
~~~

Without a null check, downstream can fail with NullPointerException. This is a **bug in the callback code**, not a bug in the completedStage(null) factory.

### Exception Classification

- **Input validation error:** can use failedStage/failedFuture from the start.
- **Error inside callback:** makes downstream exceptional.
- **Cancellation:** a special state of Future, not necessarily the same semantics as a business error.
- **Timeout waiting for result:** the caller's deadline expires, though the computation may continue.
- **Error from an external service:** needs a cause, retry/idempotency policy, and is not cured automatically by a factory.

**Do not catch every Throwable and return "OK"** if the caller needs to distinguish data errors from programming bugs or infrastructure errors.

## 16. exceptionallyCompose: When the Fallback Is Also a Stage

**exceptionally(fn)** lets you produce a **normal value** from an error. Sometimes, however, the fallback needs to call an API that returns a CompletionStage. Java 17 provides **exceptionallyCompose**, which allows the callback to return a **CompletionStage<T>** and then flattens it.

~~~java
// Illustrative snippet for a CompletionStage<String> source.
CompletionStage<String> recovered =
        source.exceptionallyCompose(error ->
                CompletableFuture.completedStage("backup")
        );
~~~

**thenCompose** runs on the success branch; **exceptionallyCompose** runs on the error branch. Both allow chaining stages without creating nested CompletionStages for the caller.

### Example 8: exceptionallyCompose Recovering from failedStage

File **ExceptionallyComposeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ExceptionallyComposeDemo {
    public static void main(String[] args) {
        CompletionStage<String> failed =
                CompletableFuture.failedStage(
                        new IllegalStateException("primary failed")
                );

        CompletionStage<String> recovered =
                failed.exceptionallyCompose(error ->
                        CompletableFuture.completedStage("backup")
                );

        System.out.println("value = "
                + recovered.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExceptionallyComposeDemo.java
java ExceptionallyComposeDemo
~~~

Stdout:

~~~text
value = backup
~~~

The primary error is replaced by the backup result. If backup also fails, recovered remains exceptional. **There is no automatic infinite retry**: calling join again on the same stage does not re-issue a request.

A real retry mechanism must create a new attempt, with attempt limits, deadlines, backoff, and idempotency for side effects.

## 17. A Mutable Value in completedStage Does Not Become Immutable

A completed factory **holds a reference to the value**; it **does not deep-copy** every result object.

~~~java
StringBuilder mutable = new StringBuilder("A");
CompletionStage<StringBuilder> stage =
        CompletableFuture.completedStage(mutable);
mutable.append("B");
~~~

Reading the stage later receives a reference to the same StringBuilder containing "AB". If another thread modifies the same StringBuilder concurrently, there is no thread-safety guarantee merely because the object was published via CompletableFuture.

### Example 9: A Completed Result Is Still the Same Object

File **MutableCompletedResultDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class MutableCompletedResultDemo {
    public static void main(String[] args) {
        StringBuilder original = new StringBuilder("A");

        CompletionStage<StringBuilder> stage =
                CompletableFuture.completedStage(original);

        original.append("B");

        StringBuilder returned =
                stage.toCompletableFuture().join();

        System.out.println("same object = " + (returned == original));
        System.out.println("value = " + returned);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableCompletedResultDemo.java
java MutableCompletedResultDemo
~~~

Stdout:

~~~text
same object = true
value = AB
~~~

The example runs only on main so the output is deterministic; it **does not prove StringBuilder is safe when modified concurrently by multiple threads**.

When providing results to multiple continuations, consider an **immutable record**, immutable collections, defensive copies, or clearly designed ownership. A **final field** holding a reference to a mutable object does not make that object immutable.

## 18. A Null Throwable Is Not a Valid Failed Completion

**failedFuture(exception)** and **failedStage(exception)** require a non-null Throwable argument. Passing null does not create an "empty error"; it causes an API usage error.

Conversely, **completedFuture(null)** or **completedStage(null)** is a normal completion with a null value.

### Example 10: Comparing Null Result and Null Exception

File **NullFactoryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class NullFactoryDemo {
    public static void main(String[] args) {
        boolean failedFutureRejected = false;
        boolean failedStageRejected = false;

        try {
            CompletableFuture.<String>failedFuture(null);
        } catch (NullPointerException ex) {
            failedFutureRejected = true;
        }

        try {
            CompletableFuture.<String>failedStage(null);
        } catch (NullPointerException ex) {
            failedStageRejected = true;
        }

        System.out.println("failedFuture null rejected = "
                + failedFutureRejected);
        System.out.println("failedStage null rejected = "
                + failedStageRejected);
        System.out.println("completed null = "
                + (CompletableFuture.completedStage(null)
                    .toCompletableFuture().join() == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullFactoryDemo.java
java NullFactoryDemo
~~~

Stdout:

~~~text
failedFuture null rejected = true
failedStage null rejected = true
completed null = true
~~~

**Be careful with generic inference:** When declaring the result type explicitly, the compiler gets type information from the assignment or explicit type parameter. Do not use null as an undefined API signal, as it easily causes callbacks to dereference null.

## 19. Cancellation Is Not the Same as failedFuture with a Regular Error

**Cancellation** is a Future state. If you cancel an **incomplete** CompletableFuture, get/join can throw CancellationException and isCancelled() is true. Meanwhile:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("invalid")
        );
~~~

...then failed.isCancelled() is false. It completed exceptionally, not in a cancelled state.

**Calling cancel after the Future has already completed/failed** cannot alter an already-decided completion. Completed/failed factories do not create a background task for cancel(true) to interrupt.

### Can failedFuture(Throwable) Accept CancellationException as Cause?

The API accepts a Throwable; however, **do not manually wrap CancellationException as a workflow substitute for the cancel protocol** when business logic needs to distinguish FAILED and CANCELLED. Different CompletableFuture paths can have specific state effects, and what matters is that the application's **state contract** is clearly defined.

### Timeout Does Not Turn failedFuture into Success

Future.get(timeout) on a pending Future can throw TimeoutException. With an already-completed failedFuture, waiting reads the failure immediately; a timeout does not automatically retry, fix the result, or cancel side effects.

## 20. getNow Is Not an Error-Recovery Method

On CompletableFuture:

- **getNow(defaultValue)** returns the result if completed normally.
- If not yet complete, it returns the default value.
- If completed exceptionally, it **throws a completion exception**; it is not a dedicated fallback for errors.

Therefore, do not write:

~~~java
// Wrong intent: assuming the default value is always returned on error.
String value = failed.getNow("default");
~~~

In this illustrative snippet, failed is an exceptional CompletableFuture<String>. getNow can throw an exception instead of returning "default".

To provide a fallback for errors, use **exceptionally**, **handle**, or explicit exception handling.

## 21. toCompletableFuture and State Control Capabilities

**CompletionStage.toCompletableFuture()** converts from the pipeline interface to a full CompletableFuture for interop or Future methods.

However, distinguish carefully:

- Minimal stages from completedStage/failedStage may be represented by objects that only support CompletionStage operations.
- toCompletableFuture creates/provides a CompletableFuture with the corresponding completion; **it is not required to always be the exact same object identity**.
- If an API returns CompletionStage to hide the source's complete/cancel privileges, the caller must not assume that completing/cancelling an adapter will change the original upstream.
- For an ordinary original CompletableFuture, the toCompletableFuture implementation may return that same object. Therefore, do not assert object identity for **all** CompletionStage implementations.

**A proper contract should speak in terms of results and dependency rules**, not rely on the implementation class of a minimal stage.

## 22. An API with Cache Hit and Immediate Error Paths

Suppose a method returns CompletionStage<User>. A common design is:

~~~java
// Illustrative snippet; User, cache, and fetchAsync are declared by the application.
CompletionStage<User> loadUser(String id) {
    if (id == null || id.isBlank()) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("id required")
        );
    }

    User inCache = cache.get(id);
    if (inCache != null) {
        return CompletableFuture.completedStage(inCache);
    }

    return fetchAsync(id);
}
~~~

This approach has three paths:

1. **Validation fail:** returns a failed stage without immediately throwing a domain error to the caller.
2. **Cache hit:** returns a completed stage without creating a fake task.
3. **Cache miss:** returns a stage for actual I/O, which may be pending.

The caller handles all three uniformly:

~~~java
CompletionStage<String> response =
        loadUser(id)
            .thenApply(User::displayName)
            .exceptionally(error -> "unavailable");
~~~

This is an illustrative code snippet, not a standalone file. If the cache holds a mutable User object modified by another thread, **completedStage does not lock User**; safe publication and ownership still need to be addressed separately.

### Do Not Turn Every Error into the Same Value

A fallback value like "unavailable" may be reasonable for a UI, but should not be used where you need to distinguish **invalid input**, **not found**, **timeout**, **unauthorized**, or **internal failure**. The recovery strategy must fit the domain.

## 23. Comparison with new CompletableFuture and Manual Completion

You can create a pending Future:

~~~java
CompletableFuture<Integer> future = new CompletableFuture<>();
future.complete(42);
~~~

If the result is already available, **completedFuture(42)** is shorter and clearer.

Similarly:

~~~java
CompletableFuture<Integer> future = new CompletableFuture<>();
future.completeExceptionally(
        new IllegalStateException("failure")
);
~~~

When the error is already known, **failedFuture** expresses the intent clearly.

### When Is a Pending CompletableFuture Actually Needed?

If an event **will arrive in the future** and a callback will complete the promise, creating a pending CompletableFuture makes sense. In that case you need to:

- Define who is the **owner of complete/completeExceptionally**.
- Avoid exception/timeout branches that forget to complete the future and leave the caller waiting forever.
- Have appropriate deadlines/cancellation/cleanup.
- Avoid completing multiple times with conflicting results; by contract, only one completion wins.
- Not use completedStage to pretend to wait for I/O when no result exists yet.

**Completed/failed factories solve cases where the outcome is already known**, rather than replacing the entire asynchronous computation mechanism.

## 24. Common Mistakes

| Misconception | Correction |
| --- | --- |
| completedStage creates a new Thread | No; it creates an already-completed stage |
| failedFuture throws an exception immediately at the call site | Normally returns an exceptional Future |
| completedStage and completedFuture have different results | Same normal result, different public return type |
| failedStage and failedFuture differ in error timing | Both are immediately exceptional, different API surface |
| completedStage(null) is a failed stage | null can be a normal result |
| failedStage(null) is a failure with no cause | Error factories require a non-null Throwable |
| A minimal CompletionStage can always be cast and completed | Do not rely on the runtime implementation |
| toCompletableFuture always returns the same instance | Not guaranteed for every stage |
| thenApply runs even if upstream failed | No; success-only callbacks are skipped |
| exceptionally always runs | Only called for an exceptional upstream |
| whenComplete turns an error into success | Does not recover by default |
| handle only runs on error | Runs on both normal and exceptional outcomes |
| thenCompose creates a two-level nested stage | The result is flattened |
| thenApply on completedStage definitely runs in the background | Can run immediately on the registering thread |
| thenApplyAsync creates a new thread every time | The executor can reuse worker threads |
| isDone=true means successful | Done includes errors and cancellation |
| get and join throw the same wrapper | get uses ExecutionException, join uses CompletionException |
| getNow(default) hides errors | If already exceptional, it can throw an error |
| Calling join again will retry | No, it only observes the fixed completion |
| completedStage makes the result immutable | No, it holds a reference |
| failedFuture logs the error automatically | Does not replace a telemetry system |
| Timeout automatically cancels | No; timeout waiting is separate from cancel |

## 25. Factory Selection Decision Table

| API need | Choice | Why |
| --- | --- | --- |
| Already-succeeded stage, expose composition only | **completedStage(value)** | Returns minimal CompletionStage |
| Already-failed stage, expose composition only | **failedStage(ex)** | Unifies CompletionStage-typed APIs |
| Already-succeeded Future, caller needs CompletableFuture | **completedFuture(value)** | Full concrete Future |
| Already-failed Future, caller needs CompletableFuture | **failedFuture(ex)** | Exceptional concrete Future |
| Truly pending computation | **new CompletableFuture** or another async API | Needs owner/lifecycle to complete later |
| Callback wants to map to a result | **thenApply** | Success path only |
| Callback wants another stage | **thenCompose** | Flattens dependent stage |
| Fallback with a value | **exceptionally** | Exceptional path recovery |
| Fallback with another stage | **exceptionallyCompose** | Flattens fallback stage |
| Need to inspect both success/error | **handle** | Can produce a new result |
| Telemetry/cleanup only | **whenComplete** | Does not recover by default |

**More important than choosing a factory:** you must define the **public API type**, completion ownership, exceptional workflow, executor context, and result correctness.

## 26. Performance and Scheduling Guarantees

Because the factories return already-completed stages:

- No queued computation is created merely by calling the factory.
- No thread is created merely by calling the factory.
- No waiting on a timer or external service is needed for the state to complete.
- However, **Async continuations** may schedule work onto a separate executor.
- **Non-Async continuations** may run immediately on the caller and block the caller if the callback is slow.
- Attaching a very large number of dependent stages still incurs allocation/processing overhead.
- An already-failed stage does not mean downstream cannot do work: recovery callbacks will still be invoked.

**Do not use completedStage as an asynchronous performance benchmark tool.** If you need to compare callbacks on workers, choose a specific executor and measure workload/queue/latency/GC with appropriate methodology.

### Async Executor Failures

If you use thenApplyAsync with an executor that is already shut down or overloaded, the dependent stage can fail because it cannot be scheduled. A **normal upstream completedStage** does not guarantee every dependent stage will be normal.

## 27. Java Memory Model and Value Ownership

Using CompletionStage does not eliminate requirements for **happens-before** and thread safety.

- When a stage's result is completed, dependent actions can observe the value according to the synchronization guarantees of Future/CompletableFuture.
- **Future.get()** has memory consistency effects corresponding to the actions of the completing computation.
- However, if the value is a mutable object and another thread **continues modifying the object after completion**, concurrent reads/writes require separate locking/atomics/immutable ownership.
- Callbacks may run on different threads; ThreadLocal context does not automatically follow each stage.
- Do not pass a mutable List to multiple callbacks that add/remove concurrently and assume CompletionStage serializes all access.

A safe API typically returns an **immutable snapshot** with immutable components or clearly specifies which caller has permission to mutate state.

## 28. Review Checklist

**API and Types:**

- [ ] Is it clear whether the method returns CompletionStage or CompletableFuture?
- [ ] Are completedStage/failedStage used when you only want callers to compose?
- [ ] Are completedFuture/failedFuture used when a concrete CompletableFuture is genuinely needed?
- [ ] Are minimal stages never cast to call methods outside CompletionStage?
- [ ] Is there no assumption that toCompletableFuture returns the same object?
- [ ] Are null results and null exceptions specified?

**Pipeline:**

- [ ] Are thenApply/thenCompose properly skipped when upstream fails?
- [ ] Are exceptionally/handle placed where recovery is needed?
- [ ] Is whenComplete not mistaken for a recovery method?
- [ ] Are get/join exception wrappers handled properly?
- [ ] Can callbacks throw on their own and create a failed downstream?
- [ ] Can fallbacks fail, and are retries bounded?

**Concurrency and Business Logic:**

- [ ] Is there no assumption that non-Async callbacks run in the background?
- [ ] Is the executor in Async callbacks alive and with sufficient capacity?
- [ ] Is the result immutable or does it have thread-safe ownership?
- [ ] Is isDone not treated as domain success?
- [ ] Is timeout not treated as cancel or rollback?
- [ ] Is there telemetry/error classification for exceptional completion?

## 29. Self-Check Questions

**1. What type does completedStage(value) return?**  
A CompletionStage<U> that has already completed successfully, with no new task created by the factory.

**2. What type does failedFuture(ex) return?**  
A CompletableFuture<U> that has already completed exceptionally with the exception; it has get/join/status methods.

**3. How does failedStage(ex) differ from failedFuture(ex)?**  
failedStage's public API is a minimal CompletionStage; failedFuture is a full CompletableFuture. Both are already failed immediately.

**4. Is completedStage(null) an error?**  
No, null is an allowed normal result.

**5. Does failedStage(null) mean an empty error?**  
No. The factory requires a non-null Throwable and throws NullPointerException for the invalid argument.

**6. Why does thenApply not run when upstream has failed?**  
It is a success-only continuation. It has no normal value to transform.

**7. To fall back from an exceptional upstream with a String, what do you use?**  
exceptionally or handle, depending on the contract.

**8. To fall back with another CompletionStage, what do you use in Java 17?**  
exceptionallyCompose or an equivalent composition recovery.

**9. Does whenComplete recover from an error just because the callback logs it?**  
No; when the callback runs normally, the exceptional outcome is still preserved.

**10. How do join and get differ for ordinary errors?**  
join throws unchecked CompletionException; get throws checked ExecutionException and can throw InterruptedException.

**11. Does completedStage guarantee that thenApply runs on a separate thread?**  
No. A non-Async continuation can run on the registering thread.

**12. Does thenApplyAsync with an executor create a new thread for each callback?**  
No. The executor can reuse an existing worker pool and may have a rejection policy.

**13. Does completedStage(StringBuilder) automatically deep-copy the object?**  
No, it holds the reference; a mutable StringBuilder remains non-thread-safe when modified by multiple threads.

**14. Does toCompletableFuture always return the same object instance?**  
No, it depends on the implementation; a minimal stage may create a new CompletableFuture.

**15. Does a failedFuture automatically retry when join is called multiple times?**  
No. It has already failed; join only observes the final state.

**16. If an API has a cache hit or early validation failure, is it necessary to create supplyAsync?**  
Not required; completedStage and failedStage keep the return type consistent without creating fake tasks.

## 30. Conclusion

**completedStage()**, **failedFuture()**, and **failedStage()** represent **already-known outcomes** as Java concurrency completions:

- **completedStage(value):** normal completion, exposes a minimal CompletionStage.
- **failedFuture(ex):** exceptional completion, exposes a full CompletableFuture.
- **failedStage(ex):** exceptional completion, exposes a minimal CompletionStage.
- **completedFuture(value):** normal completion, exposes a full CompletableFuture.

Remember that **completion is distinct from execution**, **CompletionStage is distinct from concrete CompletableFuture**, and **normal is distinct from exceptional**. When assembling pipelines, distinguish **thenApply/thenCompose** for success, **exceptionally/handle/exceptionallyCompose** for recovery, and **whenComplete** for observation; handle get/join wrappers properly and do not overlook thread safety of result objects.

A good asynchronous API does not force thread creation for every path: if a value is already available, return a completed stage; if an error is already present, return a failed stage; and only when there is truly a pending computation should you use an appropriate scheduling/lifecycle mechanism.
