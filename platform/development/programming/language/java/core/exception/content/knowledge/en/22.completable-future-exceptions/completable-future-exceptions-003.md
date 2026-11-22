# get throws ExecutionException, join typically throws CompletionException

## 1. The problem: one CompletableFuture, multiple ways to receive errors

**CompletableFuture<T>** can complete in one of the main outcomes: succeed with a value, complete exceptionally with an exception, or be canceled. Two common methods to wait for and retrieve the result are **get()** and **join()**. When a CompletableFuture completes successfully, both return a value of type T. When a CompletableFuture completes exceptionally, **the way they report errors differs**.

- **get()** inherits the contract of **Future**: for typical task failures, it throws **ExecutionException**, a **checked exception**, and places the root error in **getCause()**.
- **join()** has a more convenient contract for pipelines: for typical task failures, it throws **CompletionException**, an **unchecked exception**, with the cause in **getCause()**.
- The two statements above are **general rules**, not rules that apply regardless of state. For a **canceled** CompletableFuture, both **get()** and **join()** can throw **CancellationException** directly. **get()** can also throw **InterruptedException** if the waiting thread is interrupted; **get(timeout, unit)** can throw **TimeoutException** directly when the wait times out.

It is essential to distinguish between the **root error of the work** and the **exception class used to propagate the error result to the consumer**. If an asynchronous task fails with **IllegalStateException("storage unavailable")**, a consumer calling get typically catches ExecutionException, while the cause to handle is IllegalStateException in the cause. For the same task, a consumer calling join typically catches CompletionException, and the cause is still IllegalStateException.

Choosing get or join is a choice about **API contract and wait control**, not something that changes the nature of the failed task. In Java Core programming, understanding how exceptions are wrapped and unwrapped helps avoid losing the error cause, mistakenly retrying cancellation, or swallowing interrupt signals.

## 2. Exception classes and API contracts

In Java 17, the relevant types belong to the **java.util.concurrent** package:

| Exception type | Checked or unchecked? | Typical role |
| --- | --- | --- |
| **ExecutionException** | Checked; extends **Exception** | Execution failure reported via **Future.get()**; the actual error is usually in the cause |
| **CompletionException** | Unchecked; extends **RuntimeException** | Exceptional completion error reported via **CompletableFuture.join()** or a CompletionStage pipeline |
| **CancellationException** | Unchecked; extends **IllegalStateException** | The Future was canceled; not all paths wrap it in ExecutionException/CompletionException |
| **InterruptedException** | Checked; belongs to **java.lang** | The caller thread was interrupted while waiting with an interruptible API, such as get() |
| **TimeoutException** | Checked | **get(timeout, unit)** could not retrieve the result within the given time |

Common signatures, written as API descriptions:

~~~java
// Illustrative signatures; these are methods of CompletableFuture<T>.
T get() throws InterruptedException, ExecutionException;

T get(long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;

T join();
~~~

Even though the signature of **join()** does not declare checked exceptions, the method can still throw **CompletionException** or **CancellationException** at runtime. Not seeing **throws** on the signature does not mean the task cannot fail.

**ExecutionException** and **CompletionException** are *wrappers* commonly used to separate the result-retrieval layer from the error that occurred inside the task. They do not mean the original error has disappeared; the caller needs to extract and preserve the cause.

## 3. Both methods receive a successful result the same way

For a CompletableFuture that has succeeded:

~~~java
// Standalone expression illustration, placed inside a Java method.
CompletableFuture<String> future =
        CompletableFuture.completedFuture("ready");

String fromGet = future.get();
String fromJoin = future.join();
~~~

Both **fromGet** and **fromJoin** equal **"ready"**. The differences become clear when the result is not yet ready or completes exceptionally:

- **get()** can be interrupted while waiting, so the caller must handle or declare InterruptedException.
- **join()** does not declare InterruptedException like get; it does not return through an equivalent checked-interruption branch.
- **get()** requires handling ExecutionException via the checked exception mechanism.
- **join()** lets CompletionException propagate via the unchecked exception mechanism; this is convenient in methods/lambdas that do not declare checked exceptions, but an error-reporting strategy is still required at an appropriate boundary.

Do not choose join merely to "avoid writing catch" if the application genuinely needs a cancellation policy, deadline, or error-cause handling. Conversely, it is not necessary to catch ExecutionException at every layer when the get contract can be propagated to the responsible boundary.

## 4. Complete Java 17+ example: verifying wrapper classes and causes

The program below creates four scenarios **independent of any scheduler**: a succeeded Future, a Future completed exceptionally with an existing IllegalStateException instance, a canceled Future, and a timed get call on an incomplete Future.

Save the following content as **GetJoinExceptionsDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class GetJoinExceptionsDemo {
    static void describe(Throwable failure) {
        Throwable cause = failure.getCause();
        System.out.println(failure.getClass().getSimpleName()
                + " | cause=" + (cause == null ? "none"
                        : cause.getClass().getSimpleName() + ": " + cause.getMessage()));
    }

    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("ready");
        System.out.println("success get=" + readGet(success));
        System.out.println("success join=" + success.join());

        IllegalStateException original =
                new IllegalStateException("storage unavailable");
        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(original);

        try {
            failed.get();
        } catch (ExecutionException failure) {
            describe(failure);
            System.out.println("get keeps original cause=" + (failure.getCause() == original));
        }
        try {
            failed.join();
        } catch (CompletionException failure) {
            describe(failure);
            System.out.println("join keeps original cause=" + (failure.getCause() == original));
        }

        CompletableFuture<String> canceled = new CompletableFuture<>();
        canceled.cancel(false);
        try {
            canceled.get();
        } catch (ExecutionException failure) {
            describe(failure);
        } catch (CancellationException failure) {
            System.out.println("canceled get=" + failure.getClass().getSimpleName());
        }
        try {
            canceled.join();
        } catch (CancellationException failure) {
            System.out.println("canceled join=" + failure.getClass().getSimpleName());
        }

        CompletableFuture<String> waiting = new CompletableFuture<>();
        try {
            waiting.get(1, TimeUnit.MILLISECONDS);
        } catch (ExecutionException failure) {
            describe(failure);
        } catch (TimeoutException failure) {
            System.out.println("timed get=" + failure.getClass().getSimpleName());
        }
        waiting.complete("later");
        System.out.println("later join=" + waiting.join());

        CompletableFuture<String> downstream =
                failed.exceptionally(failure -> "fallback");
        System.out.println("recovered=" + downstream.join());
        System.out.println("original failed=" + failed.isCompletedExceptionally());
    }

    static String readGet(CompletableFuture<String> future)
            throws InterruptedException {
        try {
            return future.get();
        } catch (ExecutionException failure) {
            throw new AssertionError("Unexpected failure", failure);
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 GetJoinExceptionsDemo.java
java GetJoinExceptionsDemo
~~~

Stdout verified directly when running the program:

~~~text
success get=ready
success join=ready
ExecutionException | cause=IllegalStateException: storage unavailable
get keeps original cause=true
CompletionException | cause=IllegalStateException: storage unavailable
join keeps original cause=true
canceled get=CancellationException
canceled join=CancellationException
timed get=TimeoutException
later join=later
recovered=fallback
original failed=true
~~~

### Why does it produce this output?

The **original error** is created exactly once:

~~~java
IllegalStateException original =
        new IllegalStateException("storage unavailable");
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(original);
~~~

This is an excerpt from the full program. **completeExceptionally(original)** transitions the Future's state to exceptionally completed with the provided Throwable. It does not mean a Callable body just threw an error; it is a way to explicitly complete a CompletableFuture with an exception.

When the consumer calls **failed.get()**, the observed wrapper is ExecutionException and **getCause() == original** evaluates to true. Calling **failed.join()** on that same Future reports the error via CompletionException, yet **getCause() == original** is still true. The original error does not change its type or message just because the consumer chooses a different API.

When **cancel(false)** is called successfully on an incomplete Future, both get and join throw CancellationException directly. This code does not claim that cancellation always takes the same form across all dependent stages; a dependent stage may be completed exceptionally with a wrapper whose cause is CancellationException.

In the timeout section, **waiting.get(1, MILLISECONDS)** times out because no thread or code completes waiting beforehand. After catching TimeoutException, the program calls **waiting.complete("later")**, so **waiting.join()** returns **later**. A wait timeout does not automatically cancel the Future.

Finally, **failed.exceptionally(failure -> "fallback")** creates a downstream stage that completes normally with **fallback**, while **failed.isCompletedExceptionally()** remains true. A recovery stage does not turn the upstream Future's state into success.

## 5. ExecutionException: the task error is in the cause

When **Future.get()** retrieves the result from a task that completed exceptionally due to a normal execution error, the caller receives **ExecutionException**. For example:

~~~java
// Contextual illustration code; failed is CompletableFuture<String>.
try {
    String result = failed.get();
    use(result);
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    handleTaskFailure(original);
}
~~~

This snippet is a method body; it needs to additionally declare or catch **InterruptedException**, and **use/handleTaskFailure** are application functions; it is not yet a standalone runnable program.

Key distinctions to make:

1. **ExecutionException** describes the failure to retrieve a result because the task completed exceptionally.
2. **Cause** describes the error that caused the task to fail, such as IllegalArgumentException, IOException, or IllegalStateException.
3. The **stack trace** of the wrapper usually relates to the point of result retrieval, whereas the stack trace of the cause shows where the original error occurred.
4. **isCompletedExceptionally()** indicates that the Future completed exceptionally, but it does not replace classifying the cause.
5. If code re-wraps the exception to cross an abstraction layer, it must preserve the cause so as not to lose error history.

For example, a service layer wants to report an error with business context:

~~~java
// Illustration of a method that can declare InterruptedException.
try {
    return future.get();
} catch (ExecutionException e) {
    throw new IllegalStateException("Could not load profile", e.getCause());
}
~~~

Here the business wrapper preserves the original cause, though choosing between **e.getCause()** or **e** as the cause should be weighed based on diagnostic needs. Keeping **e** preserves both the Future wrapper and the underlying original; using **e.getCause()** makes the business wrapper point directly to the task error. Both can be reasonable as long as no information is lost. Strictly avoid throwing just **new IllegalStateException(e.getMessage())** and dropping the cause.

## 6. CompletionException: join's unchecked error-reporting mechanism

**CompletableFuture.join()** does not force the caller to declare checked ExecutionException or InterruptedException. If the Future completes exceptionally due to a normal task error, join throws **CompletionException** with the original error as the cause.

~~~java
// Contextual illustration code.
try {
    String result = future.join();
    use(result);
} catch (CompletionException e) {
    Throwable original = e.getCause();
    handleTaskFailure(original);
}
~~~

This is an appropriate handling branch when the caller is allowed to work with unchecked exceptions and does not need get's interruption-controlled contract. However, do not assume **catch(CompletionException)** covers every failure of join: when a Future is canceled, **CancellationException** can be thrown directly.

**CompletionException** commonly appears in pipelines of **thenApply**, **thenCompose**, **thenCombine**, **handle**, and other dependent CompletionStages. A lambda in thenApply may throw IllegalArgumentException; the stage completes exceptionally and when join is called at the end of the pipeline, the consumer receives a CompletionException whose cause is the error from the lambda.

Example:

~~~java
// Illustrative snippet that can be placed inside a method.
CompletableFuture<Integer> pipeline =
    CompletableFuture.completedFuture("not-a-number")
        .thenApply(Integer::parseInt);

try {
    pipeline.join();
} catch (CompletionException failure) {
    System.out.println(failure.getCause().getClass().getSimpleName());
}
~~~

This snippet prints **NumberFormatException** when run normally with Java 17, because Integer.parseInt cannot parse the given string. The takeaway is that the parse error can still be retrieved via **getCause()**, even though it occurred in a stage and was then received via join.

Do not use **CompletionException** as a synonym for "task error"; it is the wrapper type propagated by the completion mechanism. The application needs to inspect the actual cause and check whether an earlier stage already wrapped another exception.

## 7. When the Throwable is already a CompletionException

Not every failed Future holds the original exception directly. A method might call **completeExceptionally(new CompletionException(original))**, or a dependent stage might receive an already-wrapped error state.

According to CompletableFuture semantics, when retrieving the result from a completion containing a **CompletionException** with a cause, **get()** typically represents the error as an **ExecutionException** whose **cause is the wrapped cause**. **join()** typically propagates the existing **CompletionException**. This allows both APIs to maintain their error-reporting contracts without necessarily creating an extra wrapper layer on every result retrieval.

Therefore, the diagnostic path can have multiple layers:

~~~text
Failed Future
    |
    +-- get()  -> ExecutionException
    |              └── cause -> IllegalArgumentException
    |
    +-- join() -> CompletionException
                   └── cause -> IllegalArgumentException
~~~

The diagram above illustrates the typical case. With application logic that wraps across multiple layers, the cause chain can be deeper. Do not blindly write **e.getCause().getCause()** assuming a second level always exists; **getCause()** can return null on a custom exception without a cause.

If you need to find the root cause in your system, you can write a bounded unwrap function for known wrappers. Do not strip every wrapper regardless of type, because each wrapper can carry useful context, suppressed exceptions, or stack traces.

## 8. Important exception: CancellationException

**CancellationException** is an unchecked exception. For a **CompletableFuture canceled directly** via **cancel(...)**, both **get()** and **join()** can throw CancellationException directly. If you only catch ExecutionException or CompletionException, the application will miss the cancellation path.

~~~java
// Illustrative code:
CompletableFuture<String> canceled = new CompletableFuture<>();
boolean accepted = canceled.cancel(true);
System.out.println(accepted);
System.out.println(canceled.isCancelled());
~~~

If cancel wins the race before the Future completes, both **accepted** and **isCancelled()** are true. Afterward, **get()** and **join()** throw CancellationException.

You must distinguish between Future cancellation and the worker having stopped execution. For CompletableFuture, the **mayInterruptIfRunning** parameter of **cancel(boolean)** is not used to control interruption of the computation the way FutureTask does. If the computation runs via **supplyAsync**, the Future being canceled does not guarantee that the running supplier was interrupted or stopped producing side effects.

A stage **dependent** on a canceled Future may have a different error form:

~~~java
// Illustration; does not need to run standalone.
CompletableFuture<String> root = new CompletableFuture<>();
CompletableFuture<Integer> dependent = root.thenApply(String::length);
root.cancel(false);
// dependent may complete exceptionally with a CompletionException
// whose cause is CancellationException, rather than dependent itself being canceled.
~~~

Therefore, when determining cancellation policy, check **isCancelled()** on the right Future and inspect the cause chain on dependent stages. Do not rely on a single catch CancellationException as a guarantee that all forms of cancellation propagation have been handled.

If the task already had side effects before being canceled, do not infer that all side effects were rolled back. This is an important reason to tie cancellation policy to task ownership and business state.

## 9. Exception specific to get: InterruptedException

**CompletableFuture.get()** can throw InterruptedException when the **thread calling get** is interrupted while waiting. This is a signal intended for the waiting caller and **does not by itself prove** that the supplier or worker running that Future was canceled.

Example of a propagation policy when the signature permits:

~~~java
// Method illustration.
static String waitFor(CompletableFuture<String> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
~~~

Here the method contract allows passing InterruptedException up to the caller. There is no need to catch it at an intermediate layer and ignore it, as doing so can lose the interrupt request.

If checked exceptions cannot be declared, for example inside **Runnable.run()**, a common policy is to restore the interrupt flag and exit:

~~~java
// Illustration inside a Runnable or callback that does not declare throws.
try {
    future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException failure) {
    handleTaskFailure(failure.getCause());
}
~~~

This snippet is contextual; **handleTaskFailure** is defined by the application and **return** assumes it is inside an appropriate void method. You should not swallow InterruptedException and keep waiting indefinitely.

**join()** does not declare InterruptedException. While waiting, join does not use the same checked InterruptedException throwing path as get; thread interruption status needs to be handled according to the JDK contract and application policy. If the application needs to respond explicitly to *caller* cancellation, get or an interruptible waiting API is a better choice.

Additionally, when a worker's **Callable** itself throws InterruptedException and the Future completes exceptionally with that error, the caller's **get()** typically receives an ExecutionException **whose cause is InterruptedException**. Do not confuse this case with the caller itself being interrupted and get throwing InterruptedException directly.

## 10. Exception specific to get(timeout): TimeoutException

**get(timeout, unit)** adds a failure path when **the wait** exceeds the duration:

~~~java
// Contextual illustration example.
try {
    return future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Result not received within this wait deadline.
    throw e;
}
~~~

When the time expires, **TimeoutException** is thrown directly; it is not wrapped in ExecutionException, because it is not an error of a task that completed exceptionally. It is an error/condition of **the wait attempt**.

A timeout does not automatically transition a CompletableFuture to canceled. In the runnable example, after **waiting.get(1, MILLISECONDS)** times out, calling **waiting.complete("later")** still succeeds and **waiting.join()** returns the result.

Distinguish this from **CompletableFuture.orTimeout(timeout, unit)**:

- **future.get(timeout, unit)**: the caller stops waiting when the time expires; the Future itself may still be incomplete.
- **future.orTimeout(timeout, unit)**: if the Future has not completed when the deadline expires, the method makes **that Future itself** complete exceptionally with a TimeoutException.
- After **orTimeout** actually triggers, **future.get()** typically throws ExecutionException **with TimeoutException as its cause**, while **future.join()** typically throws CompletionException **with TimeoutException as its cause**.
- **future.completeOnTimeout(fallback, timeout, unit)** can complete the Future normally with a fallback if the deadline arrives and the Future is still not done.

In other words, TimeoutException can be a **direct exception from get(timeout)** or the **cause of an exceptional completion** observed via get/join. Using a single catch TimeoutException for all cases can cause the code to miss the cause-wrapped path.

Do not assume that orTimeout or completeOnTimeout interrupts the supplier or rolls back the running task. They determine the completion state of the CompletableFuture; the underlying execution may continue running.

## 11. isDone and isCompletedExceptionally do not identify the cause

State methods help with observation, but they do not replace reading the result and classifying the Throwable:

- **isDone()** is true when the Future has completed, including exceptional completion or cancellation.
- **isCompletedExceptionally()** is true if the CompletableFuture completed exceptionally, including cancellation.
- **isCancelled()** is true if that Future was canceled according to its cancellation state.
- **get()** or **join()** provides the successful result or propagates the error for the consumer to handle.

A method that only checks:

~~~java
// Illustrative anti-pattern.
if (future.isDone()) {
    markSuccess();
}
~~~

is wrong if **markSuccess** means the task definitely succeeded. A Future can be isDone after completeExceptionally or cancel.

Nor should you conclude that **isCompletedExceptionally()** being true means a task threw an exception in its body. Code may have explicitly called **completeExceptionally(...)**, **obtrudeException(...)**, or a timeout policy may have completed the Future exceptionally.

If non-blocking result inspection is needed, other APIs such as **getNow(valueIfAbsent)** can be considered, though getNow can also throw when the Future has completed exceptionally. Choose the observation method based on state and required contract, not merely on method name.

## 12. CompletionStage chains: where do errors come from?

Consider a processing pipeline:

~~~java
// Illustrative code that can be placed inside a method.
CompletableFuture<Integer> pipeline =
    CompletableFuture.completedFuture("42")
        .thenApply(String::trim)
        .thenApply(Integer::parseInt)
        .thenApply(value -> value * 2);
int result = pipeline.join(); // 84
~~~

When every stage succeeds, join returns 84. If the input string cannot be parsed, the **Integer::parseInt** stage causes the pipeline to complete exceptionally. Downstream stages normally do not run their value transformations, and the consumer at the end receives a CompletionException. The cause helps locate the actual parse error.

Errors can originate from:

1. The initial data provider, such as the supplier of **supplyAsync**.
2. A transformation function **thenApply**.
3. An asynchronous dependency function such as **thenCompose**.
4. An observation callback **whenComplete** that throws an exception itself.
5. A deadline policy **orTimeout**.
6. Cancellation of a stage or root Future.
7. Code explicitly calling **completeExceptionally(...)**.

Therefore, when seeing CompletionException at **join()**, do not conclude that the join method itself has a bug or that the final stage is the error source. Follow the cause and pipeline context to determine which stage actually failed.

### The exceptionally recovery branch

**exceptionally(Function<Throwable, ? extends T>)** creates a stage that can convert an exceptional upstream outcome into a fallback value. For example:

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalStateException("remote unavailable"));
CompletableFuture<String> recovered =
        source.exceptionally(failure -> "cached value");
System.out.println(recovered.join());
~~~

This snippet prints **cached value**. **recovered** completes normally if the recovery function returns the fallback; **source** remains completed exceptionally. Downstream recovery does not retroactively change the upstream state.

If the exceptionally lambda throws a new exception, recovered can also complete exceptionally. Do not swallow every exception with a default fallback if the error has security implications, data integrity impact, or business requirements that forbid continuing.

### The handle branch

**handle((value, failure) -> ...)** is invoked whether upstream succeeds or fails and can transform the outcome into a new value. When **failure** is non-null, the application needs to distinguish recoverable errors from cancellation or critical failures. Having a handle callback does not mean every error should be turned into a success.

### The whenComplete branch

**whenComplete((value, failure) -> ...)** is typically used to observe side effects such as metrics/logging. It does not automatically convert an error outcome into a normal value. If the callback itself throws an error, understand how the callback's exception affects the returned stage; avoid letting logging/cleanup produce an unintended new error outcome.

## 13. How to write result handling with get()

For service layers permitted to declare checked exceptions, you can use get and let the caller decide:

~~~java
// Illustrative code inside a class.
static <T> T await(CompletableFuture<T> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
~~~

Benefit: the signature clearly communicates that the caller can be interrupted or receive a task error via ExecutionException. If the caller needs a deadline, add a variant using **get(timeout, unit)** and declare TimeoutException.

When you genuinely need to translate the error into a domain exception, read the cause carefully:

~~~java
// Contextual illustration code.
try {
    return future.get();
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    throw new IllegalStateException("Async operation failed",
                                    cause == null ? e : cause);
}
~~~

Handle **InterruptedException** according to the contract of the enclosing method. If you can propagate the checked exception, letting it bubble up is usually better than swallowing it and continuing. If you cannot, restore the interrupt flag and apply a stopping policy.

Do not catch generic **Exception** and treat every branch as a task error: that mixes **InterruptedException**, **ExecutionException**, and potentially **CancellationException** into the same business error category.

## 14. How to write result handling with join()

**join()** fits well when code consumes a synchronous pipeline at its terminal point, when the interface does not declare checked exceptions, or when the caller already has a common boundary for handling unchecked errors.

~~~java
// Illustrative code inside a class.
static <T> T joinResult(CompletableFuture<T> future) {
    try {
        return future.join();
    } catch (CancellationException canceled) {
        throw canceled;
    } catch (CompletionException failed) {
        throw failed;
    }
}
~~~

This snippet only illustrates the two error types to distinguish; in practice, if both are simply rethrown as-is, the catch blocks can be omitted. When business context needs to be added, you can wrap while preserving **failed** or **failed.getCause()** according to the API contract.

Example handling design:

~~~java
// Contextual illustration code.
try {
    return future.join();
} catch (CancellationException canceled) {
    recordCancellation(canceled);
    throw canceled;
} catch (CompletionException failed) {
    Throwable cause = failed.getCause();
    recordFailure(cause == null ? failed : cause);
    throw failed;
}
~~~

**recordCancellation** and **recordFailure** are application functions; the snippet above does not run standalone. The key point: cancellation may need its own policy rather than being recorded as a normal task failure.

Another mistake is writing **catch (CompletionException e) { return null; }** to silence every exception. If null does not represent a valid result, downstream code may throw NullPointerException and obscure the true error source. If a fallback is needed, specify clearly which exception types it applies to, and consider **exceptionally** or **handle** with consistent semantics.

## 15. When to use get and when to use join?

| Scenario | Typically suitable choice | Reason |
| --- | --- | --- |
| API already declares **InterruptedException/ExecutionException** | **get()** | Preserves the checked contract and ability to react when the caller is interrupted |
| Need to bound the wait time for a result | **get(timeout, unit)** | Direct TimeoutException for the wait attempt |
| Terminal point of a CompletionStage pipeline that should not declare checked exceptions | **join()** | CompletionException is unchecked; convenient to integrate, though errors still must be handled |
| Want a fallback when the pipeline fails | **exceptionally/handle** then get/join | Recovery in a dedicated stage with a clear policy |
| Multiple results to wait for after allOf | **allOf(...).join()** is commonly used | Wait for all, then inspect individual states; errors still need classification |
| Support caller-thread cancellation via an interruptible contract | **get()** or a suitable interruptible API | join does not provide the same checked InterruptedException path |
| Do not want to block on a request thread | Use an asynchronous pipeline | Both get and join can block; consider an async architecture |

There is no rule that **join() is always better than get()** or vice versa. Choose the API based on the boundary, error-reporting style, cancellation/wait requirements, and the type of caller being served.

In particular, **get()** is the wait mechanism that can report an interrupted caller directly; **join()** does not have a built-in timeout wait overload. If you want a timeout on a CompletableFuture without altering the Future's state, use **get(timeout)** rather than blindly calling **orTimeout**.

## 16. Blocking behavior and deadlock risks

Both **get()** and **join()** can block the calling thread when the Future has not completed. In a small thread pool, a task running on an executor that calls **join()** to wait for another task submitted to the **same executor** can cause worker starvation or deadlock.

Thought experiment: the executor has only one worker; task A is running and occupies the worker, task A waits on task B's Future using join, while B sits in the same executor's queue. If no other thread can process B, A can wait forever.

Choosing get or join does not solve this design issue by itself. You should:

- Compose dependent steps with **thenCompose**, **thenApply**, **thenCombine** instead of blocking inside a worker whenever possible.
- Use an executor sized appropriately for the concurrency level and I/O type.
- Avoid unbounded waits at boundaries that have deadlines.
- Monitor threads, queues, thread dumps, and diagnose latency if starvation signs appear.

A CompletionException arising after a timeout or task failure does not prove the bug is in get/join; the root cause may be deadlock, a timeout policy, or an earlier stage.

## 17. Logging and preserving original error details

When reporting asynchronous errors, logging should preserve the full Throwable:

~~~java
// Illustration with a logger providing logger.error(String, Throwable).
try {
    future.join();
} catch (CompletionException failed) {
    logger.error("Asynchronous operation failed", failed);
    throw failed;
}
~~~

Printing only **failed.getMessage()** may not provide enough context about the cause. A full exception tree shows the wrapper, cause, stack traces, and suppressed exceptions. If a service layer re-wraps the exception, pass the appropriate cause.

Also avoid duplicate logging at every pipeline stage and every consumer. You can let layers close to the source add context, while the final observation boundary writes one appropriate log entry. For systems using structured logging, verify whether the log pipeline preserves **cause** and **suppressed** data.

Do not expose sensitive information from exceptions directly in public APIs. You can return a generic error code response to the client while retaining the full error chain in internal logs.

## 18. Testing exact exception types and causes

A good test does not just check "an exception occurred", it checks **the right wrapper class and the right cause**.

For a CompletableFuture completed exceptionally with a specific error instance:

1. Call **get()** and assert **ExecutionException**.
2. Compare **getCause()** against the exact original error instance; comparing only the message can miss accidental exception recreation.
3. Call **join()** on the same Future and assert **CompletionException**.
4. Verify that join's cause is also the original error.
5. For a directly canceled Future, verify that both get and join throw **CancellationException**.
6. For an incomplete Future, **get(timeout)** throws **TimeoutException** and the Future remains uncanceled.
7. Complete the Future after timeout, then assert **join()** returns the result.
8. Create an **exceptionally** stage and verify that a successful fallback does not alter the upstream error state.

The Java program in section 4 demonstrates these points without relying on background scheduling; specifically, **get(1, MILLISECONDS)** waits on an incomplete Future so the timeout branch is deterministic.

Comparison table:

| Scenario | get() | join() |
| --- | --- | --- |
| Future completes normally | Value T | Value T |
| Future completes exceptionally with IllegalStateException | ExecutionException, cause IllegalStateException | CompletionException, cause IllegalStateException |
| Future is canceled directly | CancellationException | CancellationException |
| Caller is interrupted while waiting | Direct InterruptedException | Does not throw checked InterruptedException |
| Wait times out | **get(timeout)** throws TimeoutException | join has no timeout overload |
| Future completed exceptionally by **orTimeout** | ExecutionException, cause TimeoutException | CompletionException, cause TimeoutException |

For a dependent stage of a canceled CompletableFuture, the wrapper class may differ from calling get/join on the root Future; verify the right stage in each assertion.

### Testing with supplyAsync

If using **supplyAsync**, real asynchrony can introduce races into tests. To keep tests deterministic:

- Use a latch or an already-completed CompletableFuture to control timing.
- To test stage exceptions, explicitly use **completeExceptionally** or **failedFuture** with a known error instance.
- In integration tests, verify that tasks actually finish and executors are shut down when owned by the test.
- Do not use arbitrary-duration sleeps as the sole synchronization mechanism.

## 19. Common mistakes

**Catching CompletionException to handle get().** get normally throws **ExecutionException** for exceptional completion; do not write a handler for the wrong wrapper class and expect to catch all errors.

**Catching ExecutionException to handle join().** join typically throws CompletionException, which is unchecked. Match the catch type to the API actually called.

**Forgetting CancellationException.** A canceled Future can cause both get and join to throw CancellationException directly, bypassing ExecutionException/CompletionException catches.

**Assuming get and join produce two different root errors.** The task error can be the exact same Throwable, propagated through different wrappers. Read the cause to classify it.

**Catching generic Exception and swallowing InterruptedException.** The caller of get may be requested to stop. Propagate it or restore the flag and exit according to contract.

**Treating a timeout as a task error.** get(timeout) expires directly because the caller waited too long, while the task may still complete later. Distinguish this from exceptional completion caused by orTimeout.

**Using isDone() as a success flag.** isDone is also true for canceled and exceptional completion.

**Hardcoding a two-level getCause() unwrap.** The exception tree can have varying depth, or a null cause. Only unwrap known wrappers and preserve sufficient context.

**Assuming canceling a CompletableFuture immediately interrupts the computation.** Future cancellation does not by itself guarantee the supplier stops or rolls back side effects.

**Calling join inside a worker to wait for work that needs the same worker to run.** This easily causes starvation/deadlock; design pipelines and executors appropriately.

**Turning every error into an unclassified fallback.** A default value can mask invariant violations, security errors, or unconfirmed results. Recovery must have an explicit policy.

## 20. Pre-production checklist

1. Which states can the Future complete in: success, failure, canceled?
2. Does the calling boundary want get's checked exceptions or join's unchecked exceptions?
3. Does the caller need to react to interrupts and timeouts under a dedicated contract?
4. When get fails, does the code catch ExecutionException and extract the cause?
5. When join fails, does the code catch CompletionException and distinguish CancellationException?
6. If the API converted timeouts to exceptional completion via orTimeout, is it aware that the timeout error is in the wrapper's cause?
7. Does any code treat isDone() as synonymous with success or treat canceled as meaning the worker has stopped?
8. Does the pipeline have exceptionally/handle callbacks that intentionally turn errors into fallbacks?
9. When wrapping exceptions, are stack traces, causes, and suppressed exceptions still preserved?
10. Do tests verify the exact exception class, root cause, and timeout/cancellation paths?

**Key takeaway:** **CompletableFuture.get()** typically reports exceptional completion via **ExecutionException** (checked), whereas **CompletableFuture.join()** typically reports the same error via **CompletionException** (unchecked). Both must be inspected via **getCause()** to understand the task's root cause. Handle **CancellationException**, **InterruptedException**, and **TimeoutException** separately, as they describe distinct conditions and do not follow a single wrapping rule.