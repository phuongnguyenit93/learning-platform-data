# CompletableFuture: Differences Between `get()` and `join()` in Error Handling

In Java, `CompletableFuture<T>` represents a result that may become available in the future: completing normally with a value of type `T`, completing exceptionally, or being cancelled. Both `get()` and `join()` retrieve the final result and may **wait** if the future has not completed yet. The most important differences in error handling are **the exception type thrown to the caller** and **how thread interruption is handled while waiting**.

This article only covers `java.util.concurrent.CompletableFuture` and Java concurrency APIs, without going into frameworks.

## 1. Quick Comparison Table

| Scenario | `get()` | `join()` |
|---|---|---|
| Completed successfully | Returns `T` | Returns `T` |
| Not yet completed | Waits for the result; can be interrupted | Waits for the result; does not stop waiting merely because of interruption |
| Future completed exceptionally (normal failure) | Throws `ExecutionException` (checked); `getCause()` is usually the original error | Throws `CompletionException` (unchecked); `getCause()` is usually the original error |
| Future cancelled | Throws `CancellationException` directly (unchecked) | Throws `CancellationException` directly (unchecked) |
| Waiting thread is interrupted via `interrupt()` | May throw `InterruptedException` (checked) | Continues waiting and restores the interrupted flag after waiting finishes |
| Waiting for at most a given duration | Has `get(timeout, unit)`, which may throw `TimeoutException` directly (checked) | No overload accepting a timeout |
| Requires declaring `throws` or catching checked exceptions | Yes: `InterruptedException`, `ExecutionException`; timeout overload adds `TimeoutException` | No checked exceptions in the `join()` signature |

Relevant signatures:

```java
// Future<T>; CompletableFuture<T> implements Future<T>
T get() throws InterruptedException, ExecutionException;

T get(long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;

// CompletableFuture<T>
T join();
```

`ExecutionException` and `CompletionException` are primarily **asynchronous error wrappers**. They indicate that waiting for the result failed; the details of the root cause are usually in `getCause()`. Do not log only the wrapper class name and ignore the underlying cause.

## 2. Why Does the Same Future Throw Two Different Exception Types?

An asynchronous task can complete exceptionally because the function running inside throws an exception, or because the program calls `completeExceptionally(cause)`. `CompletableFuture` records that failure state. `get()` and `join()` **do not re-run the task** and do not create two independent errors: they simply interpret the same completed state according to different API contracts.

- `get()` inherits the `Future` contract. Because `ExecutionException` is a checked exception, the calling code must catch or declare it, and must also handle `InterruptedException`.
- `join()` is a convenience API on `CompletableFuture`. For ordinary failures, it uses `CompletionException`, a `RuntimeException`, making it convenient when returning results from code that does not want to declare checked exceptions.
- Both can throw `CancellationException` directly when **the future being awaited** has been cancelled. Do not assume every failure from `get()` is an `ExecutionException` or every failure from `join()` is a `CompletionException`.

### Complete Example: Same Error, Two Ways of Observing It

Save the following as `GetJoinErrorsDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class GetJoinErrorsDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("boom"));

        try {
            failed.get();
        } catch (ExecutionException e) {
            System.out.println("get(): " + e.getClass().getSimpleName()
                    + " -> " + e.getCause().getClass().getSimpleName()
                    + ": " + e.getCause().getMessage());
        }

        try {
            failed.join();
        } catch (CompletionException e) {
            System.out.println("join(): " + e.getClass().getSimpleName()
                    + " -> " + e.getCause().getClass().getSimpleName()
                    + ": " + e.getCause().getMessage());
        }

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);

        try {
            cancelled.get();
        } catch (CancellationException e) {
            System.out.println("get() cancelled: "
                    + e.getClass().getSimpleName());
        } catch (ExecutionException e) {
            throw new AssertionError("Unexpected wrapper", e);
        }

        try {
            cancelled.join();
        } catch (CancellationException e) {
            System.out.println("join() cancelled: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac GetJoinErrorsDemo.java
java GetJoinErrorsDemo
```

Output:

```text
get(): ExecutionException -> IllegalStateException: boom
join(): CompletionException -> IllegalStateException: boom
get() cancelled: CancellationException
join() cancelled: CancellationException
```

`CompletableFuture.failedFuture(...)` (available since Java 9) creates an already-failed future, keeping the example independent of thread pool timing. Reading `failed` twice shows that **the underlying cause `IllegalStateException("boom")` remains the same**, and only the wrapper depends on the calling method. `cancel(false)` creates a cancelled state; the `mayInterruptIfRunning` parameter does not make `CompletableFuture` guarantee interrupting a running task.

## 3. Extracting the Root Cause and Avoiding Catching the Wrong Type

When actively waiting with `get()`:

```java
try {
    String value = future.get();
    use(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Or propagate InterruptedException if the method contract allows it.
    throw new IllegalStateException("Thread was interrupted", e);
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    reportFailure(cause);
} catch (CancellationException e) {
    reportCancellation(e);
}
```

The snippet above is a **code pattern placed inside a method that already has** the `future` variable and `use`/`reportFailure`/`reportCancellation` methods; it is not a standalone program. Putting `CancellationException` in a separate branch is recommended because cancellation is a distinct state with its own meaning.

When actively waiting with `join()`:

```java
try {
    String value = future.join();
    use(value);
} catch (CompletionException e) {
    reportFailure(e.getCause());
} catch (CancellationException e) {
    reportCancellation(e);
}
```

If you need to convert from a checked wrapper to an unchecked wrapper while preserving the cause—for example, in an adapter layer that uses `get()`—you can write `throw new CompletionException(e.getCause())` when catching `ExecutionException`. You should establish a separate policy for handling `InterruptedException`; do not conflate interruption with task failure.

### When There Are Multiple Wrappers

In a multi-stage pipeline, an exception may already be a `CompletionException` before reaching `get()`/`join()`. If you need to identify the final business error, unwrap only the wrappers dedicated to asynchronous results:

```java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class FutureErrors {
    private FutureErrors() {}

    public static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while ((current instanceof ExecutionException
                || current instanceof CompletionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
```

This is a standalone Java 17+ class that can be saved as `FutureErrors.java`. The loop stops at the first cause that is no longer one of those two wrapper types, avoiding arbitrarily unwrapping the entire `cause` chain of every business exception. When handling errors at application boundaries, keep both the wrapper and the original stack trace in logs if they help identify which stage failed.

An `InterruptedException` thrown **inside an asynchronous task** does not mean `get()` was interrupted while waiting. The former is a failure of the task itself, usually appearing inside `ExecutionException` or `CompletionException`; the latter is a signal affecting the thread calling `get()` itself.

## 4. Interruption: Differences in Controlling the Waiting Thread

`get()` provides an *interruptible* wait: when a thread is waiting on an incomplete future and another thread calls `interrupt()` on it, `get()` can exit with `InterruptedException`. Throwing this exception normally clears the interrupted flag, so if the code catches the exception without propagating it, a common practice is to call `Thread.currentThread().interrupt()` to restore the signal for outer layers.

`join()` waits *uninterruptibly*: an interrupt does not cause `join()` to exit early with `InterruptedException`. Once the final result is available, `join()` returns the value or throws the completion error, and the interrupted flag is preserved/restored so downstream layers can observe it. This does not mean the thread or the asynchronous task will never be affected by other cancellation mechanisms.

Practical choices:

- Threads whose lifecycle must stop upon interruption (for example, a worker executing a cancellable task) generally fit `get()` with an explicit interruption policy.
- `join()` is convenient at a result-aggregation point when the intent is to wait until the future completes, but it is not suitable as a replacement for the application's cancellation/interruption mechanism.
- Do not call `Thread.interrupted()` just to "clear the flag" after `join()`: that call reads **and clears** the interrupted status, which can lose a signal meant for another layer.

**Race condition note:** if the future already has a result at the moment of the call, the fast path of `get()` may return the result before checking for interruption. Do not rely on a single race example between `complete()` and `interrupt()` to assert an absolute ordering; the key contract is that `get()` supports interruptible waiting while `join()` does not throw `InterruptedException`.

## 5. Timeout: Wait Timeout and Completion Timeout Are Not the Same

There are **two different kinds of timeout**:

1. **Caller's wait timeout:** `future.get(200, TimeUnit.MILLISECONDS)` waits for at most the specified duration. If no result is available yet, it throws `TimeoutException` directly. The future is **not automatically** marked failed or cancelled just because the caller stopped waiting.
2. **Timeout of the CompletableFuture itself:** `future.orTimeout(200, TimeUnit.MILLISECONDS)` (Java 9+) arranges for the future to complete exceptionally with `TimeoutException` if the deadline arrives before it completes. Afterward, `get()` may throw `ExecutionException` with cause `TimeoutException`; `join()` may throw `CompletionException` with cause `TimeoutException`.

These two forms have different mechanisms and scopes of impact. Standalone runnable example:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class WaitTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        CompletableFuture<String> pending = new CompletableFuture<>();

        try {
            pending.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            System.out.println("Wait timed out");
        }

        System.out.println("Future done: " + pending.isDone());
        pending.complete("ready");
        System.out.println("Later result: " + pending.join());
    }
}
```

Save as `WaitTimeoutDemo.java` and run:

```bash
javac WaitTimeoutDemo.java
java WaitTimeoutDemo
```

Output:

```text
Wait timed out
Future done: false
Later result: ready
```

No thread calls `complete()` before waiting, so the timeout in `get(20, ...)` will occur; afterward, `pending` is still incomplete. The 20 ms value is an approximate maximum wait duration, not a millisecond-exact deadline.

With `join()`, there is no `join(timeout, unit)`. If you need **the future itself** to fail when the deadline expires:

```java
CompletableFuture<String> bounded =
        new CompletableFuture<String>()
                .orTimeout(200, TimeUnit.MILLISECONDS);

try {
    bounded.join();
} catch (CompletionException e) {
    if (e.getCause() instanceof TimeoutException) {
        // The future completed exceptionally due to timeout.
    } else {
        throw e;
    }
}
```

This is a snippet inside a method that has already imported the classes in `java.util.concurrent`. `orTimeout` returns **the same future being configured**; other stages depending on it can also observe the failure state. If you want to use a default value instead of failing on timeout, see `completeOnTimeout(defaultValue, timeout, unit)`; that method completes normally with the fallback if the deadline expires first.

## 6. Handling Errors in the Pipeline Before Calling get/join

`get()`/`join()` only observe **the state of the final future**. If the pipeline has already recovered from an error, both will return a normal result. It is usually better to handle errors asynchronously using stages rather than waiting at each stage:

| Stage | When does it run? | Effect on the result |
|---|---|---|
| `exceptionally(fn)` | Only when the previous stage completes exceptionally | Returns a replacement value to recover; if the handler throws, the next stage continues to fail |
| `handle((value, error) -> ...)` | Both on success and on failure | Transforms the result or recovers in either branch |
| `whenComplete((value, error) -> ...)` | Both on success and on failure | Mainly for observation/logging; does not turn an error into success via a return value (the callback returns no result) |
| `exceptionallyCompose(fn)` | On failure; available since Java 12 | Recovers using **another asynchronous CompletionStage** |

Runnable example on Java 17+:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FutureRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> original =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("invalid input"));

        CompletableFuture<Integer> recovered = original
                .exceptionally(error -> {
                    System.out.println("Recover: "
                            + error.getClass().getSimpleName());
                    return 42;
                });

        System.out.println("Recovered value: " + recovered.join());

        try {
            original.join();
        } catch (CompletionException e) {
            System.out.println("Original still failed: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Save as `FutureRecoveryDemo.java`; compile/run:

```bash
javac FutureRecoveryDemo.java
java FutureRecoveryDemo
```

Output:

```text
Recover: IllegalArgumentException
Recovered value: 42
Original still failed: IllegalArgumentException
```

`exceptionally` creates a **new future** with the value `42` when the original branch fails; it does not mutate the state of `original`. In complex compositions, the `error` argument may already be wrapped in a `CompletionException`, so if you classify by cause, unwrap it first.

A very common pitfall: `whenComplete((v, e) -> log(e))` is **not** recovery. If the input fails and the callback only logs, the future after `whenComplete` is still failed; calling `join()` at the end of the pipeline can still throw `CompletionException`. To produce a replacement value, use `exceptionally` or `handle`.

## 7. Cancellation and Error Propagation Through Dependent Stages

A future can be cancelled via `cancel(...)`; for `CompletableFuture`, this is a form of exceptional completion. When directly reading the exact object that was cancelled, both `get()` and `join()` throw `CancellationException`. However, **dependent stages** created by `thenApply`, `thenCompose`, etc., may complete exceptionally with a `CompletionException` containing `CancellationException` as its cause.

Semantic example:

```java
CompletableFuture<String> parent = new CompletableFuture<>();
CompletableFuture<Integer> child = parent.thenApply(String::length);
parent.cancel(true);

// parent.join(): CancellationException directly.
// child.join(): may throw CompletionException,
//               with CancellationException as its cause.
```

Do not rely solely on the outer exception type to conclude "this is a business error" or "this is a task cancellation"; check `isCancelled()` on the future in question and the actual cause when needed.

`cancel(true)` on `CompletableFuture` **does not guarantee interrupting the thread executing the task**; by this class's contract, the `mayInterruptIfRunning` parameter does not control execution because interrupts are not used to manage internal execution. The task may continue running even though the future is in the cancelled state. An actual stopping mechanism must be designed separately if the work holds resources or has side effects.

## 8. Choosing get() or join() in Real Code?

- **Choose `get()`** if you are integrating with the `Future` API, need a timeout **only for the caller's wait**, or need to allow the waiting thread to react to `InterruptedException`.
- **Choose `join()`** if the code works directly with `CompletableFuture` and wants to retrieve the result at a synchronous boundary without being forced to declare checked exceptions; you still need a strategy to handle `CompletionException`/`CancellationException` when failures can occur.
- **Prefer composing stages** (`thenApply`, `thenCompose`, `handle`, `exceptionally`) when you can keep the pipeline asynchronous. Waiting in the middle of a chain easily loses non-blocking benefits and, in an executor with few threads, can cause starvation or deadlock due to tasks waiting on each other.
- When you genuinely need to aggregate multiple futures, you can use `CompletableFuture.allOf(...).join()` at the waiting boundary. It **does not** automatically provide a full report of each individual error: if you need to inspect each task, you must check each future and build an aggregation policy.

**Common mistakes to avoid:**

1. Using `catch (ExecutionException)` for `join()` or `catch (CompletionException)` for `get()` and assuming all failure branches are covered. Catch according to the API contract and remember `CancellationException`.
2. Logging only `e.toString()` on the wrapper and ignoring `e.getCause()`, losing the real error context.
3. Swallowing `InterruptedException` without propagating it or restoring the interrupt flag, making thread-stopping mechanisms fail to work properly.
4. Treating `get(timeout, unit)` as a task cancellation command; by default, it only bounds **the wait**.
5. Treating `whenComplete` as recovery handling, or using `exceptionally` to return `null` without considering the data contract of subsequent stages.
6. Catching every `RuntimeException` and silently returning a fallback, masking serious programming bugs and cancellation states.
7. Calling `join()` inside stages running on the same small executor to wait for another task that also needs that executor; this can create a wait cycle that stalls the pipeline.

## 9. Error Handling Checklist

Before choosing a method to retrieve the result, determine: **(1)** whether task completion errors should be wrapped in a checked or unchecked exception; **(2)** whether the waiting thread must react to interrupts; **(3)** whether the time limit applies to the caller or to the future itself; **(4)** whether cancellation is handled separately; **(5)** whether recovery can be performed with a stage before waiting.

For the same ordinary failed future: **`get()` → `ExecutionException` → cause**, while **`join()` → `CompletionException` → cause**. Cancellation has its own path that throws `CancellationException` directly, while interruption and timeout are conditions to evaluate based on the waiting method. Understanding these three cases helps Java code preserve the true error cause, maintain a clear cancellation policy, and avoid accidentally blocking asynchronous processing threads.
