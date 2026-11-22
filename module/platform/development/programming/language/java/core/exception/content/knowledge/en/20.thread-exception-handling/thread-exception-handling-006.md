# `Future.get()` and `ExecutionException` in Java

In concurrent programming, a task running on another thread can complete successfully, fail, or be cancelled. `Future<T>` represents a result that will be available in the future; `get()` is the point where the calling thread **waits for the result** and **observes task failures**. This lesson focuses on `Future.get()` and `ExecutionException` in Java 17+, under the topic **Exceptions and Threads**.

## 1. The Model: Where Errors Occur vs. Where They Are Observed

For example, `ExecutorService.submit(Callable<T>)` submits a task to an executor. Calling `submit()` usually returns a `Future<T>` immediately, while the task may not have started yet, may be running, or may have already finished.

```text
Calling thread                         Worker thread
--------------                         -------------
submit(callable) ────────►             waiting to be scheduled
      │                                running call()
      ▼                                │
Future<T>                              ├─ return T ─► completed successfully
      │                                └─ throw X  ─► completed with failure
      ▼
future.get()
      ├─ success ───────► receives T
      ├─ failure ───────► ExecutionException (cause = X)
      ├─ cancelled ─────► CancellationException
      └─ interrupted while waiting ─► InterruptedException
```

An exception thrown inside `Callable.call()` **does not automatically propagate to the thread that called `submit()`**. The executor records the task's failed state; when `get()` is called, the caller sees an `ExecutionException` containing the original exception in `getCause()`.

Important distinctions:

- **Task exception**: thrown in the worker; `get()` throws `ExecutionException`, with the original exception in `cause`.
- **Interrupting the waiting thread**: occurs on the thread calling `get()`; `get()` throws `InterruptedException` directly. This does not mean the task failed or was cancelled.
- **Cancelling the Future**: a successful `cancel(...)` causes `get()` to throw `CancellationException` (unchecked) directly, without wrapping it in `ExecutionException`.
- **Wait timeout**: only applies to `get(timeout, unit)`; throws `TimeoutException` when the result is not ready within the timeout period. The task is not automatically cancelled.

## 2. Two Variants of `get()` and Their Exceptions

Relevant signatures:

```java
T get() throws InterruptedException, ExecutionException;

T get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
```

`get()` without a timeout can wait indefinitely. `get(timeout, unit)` waits for at most the specified duration; `TimeoutException` signals **the caller's wait timeout**, not the worker's final completion state.

| Observed scenario | `get()` behavior | Meaning and handling |
|---|---|---|
| `Callable` returns a result | Returns `T` | Task completed successfully |
| Task throws `IOException`, `RuntimeException`, or `Error` | Throws `ExecutionException` | Inspect `getCause()` for the actual error |
| Future was successfully cancelled | Throws `CancellationException` | Handle the cancellation branch separately |
| Calling thread is interrupted while waiting | Throws `InterruptedException` | Stop/exit according to the caller's interruption policy |
| `get(timeout, unit)` has no result in time | Throws `TimeoutException` | Can continue waiting or proactively cancel |
| `get()` is called again after Future succeeded | Returns the result again | Does not re-run the task |
| `get()` is called again after Future failed | Throws `ExecutionException` again | Does not automatically retry the task |

`ExecutionException` is a **checked exception**; `InterruptedException` and `TimeoutException` are also checked exceptions. `CancellationException` extends `IllegalStateException` and is an **unchecked exception**.

`Future` also provides `isDone()` and `isCancelled()`. `isDone() == true` only indicates that the Future has terminated in one of the states **success, failure, or cancellation**; it does not guarantee that `get()` will return a result successfully. `isCancelled()` indicates whether the Future was cancelled.

## 3. Standalone Runnable Example: Success and Worker Failure

Create `FutureGetDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureGetDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> good = executor.submit(() -> 6 * 7);

            Future<Integer> bad = executor.submit((Callable<Integer>) () -> {
                throw new IllegalArgumentException("mã âm");
            });

            printResult("good", good);
            printResult("bad", bad);
        } finally {
            executor.shutdown();
        }
    }

    private static void printResult(String name, Future<Integer> future)
            throws InterruptedException {
        try {
            System.out.println(name + " = " + future.get());
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            System.out.println(name + " lỗi: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FutureGetDemo.java
java FutureGetDemo
```

Expected output:

```text
good = 42
bad lỗi: IllegalArgumentException: mã âm
```

The **actual** completion order of the two workers may vary, but the printed order remains as shown because the program calls `printResult("good", ...)` first. For `bad`, `submit()` does not immediately throw `IllegalArgumentException`; the `future.get()` call causes `ExecutionException` to appear on the `main` thread. Calling `getCause()` returns the `IllegalArgumentException` thrown in the worker. `shutdown()` is placed in `finally` to tell the executor to stop accepting new tasks even if the result-handling branch encounters an error.

Note: on Java 17, `ExecutorService` cannot yet be used directly with `try (ExecutorService executor = ...)` as an `AutoCloseable`; the `try/finally` pattern above is appropriate for Java 17.

## 4. Handling `ExecutionException`: Inspecting the Root Cause

`ExecutionException` describes that **the task failed during execution**; the actual business or technical error type is inside `getCause()`. A `Callable` is allowed to throw checked exceptions, such as `IOException`. The caller does not catch `IOException` directly from `Future.get()`, but instead observes an `ExecutionException` whose cause is `IOException`.

Inside a method processing a Future result, you can classify the cause as follows (snippet placed **inside** the `catch (ExecutionException e)` block; not a standalone program):

```java
Throwable cause = e.getCause();

if (cause instanceof IllegalArgumentException invalidInput) {
    // Classify data/input error.
    System.err.println("Đầu vào không hợp lệ: " + invalidInput.getMessage());
} else if (cause instanceof java.io.IOException ioError) {
    // Original I/O error thrown by Callable.
    System.err.println("Lỗi truy cập I/O: " + ioError.getMessage());
} else {
    // Preserve the cause chain when propagating to the application layer.
    throw new IllegalStateException("Tác vụ bất đồng bộ thất bại", cause);
}
```

Principles:

1. **Preserve the cause** when logging or wrapping: `new IllegalStateException("...", cause)`. Printing only `e.getMessage()` can lose the original exception context.
2. **Do not assume** every cause is a `RuntimeException`; a worker can throw a checked exception or an `Error`. For severe system errors, consider a dedicated handling/escalation policy rather than silently swallowing them.
3. Only **retry** with a clear strategy: calling `get()` again on the same `Future` does not re-run the task. To retry, you must submit a new task and consider idempotency, retry limits, and backoff.
4. Do not turn every error into a fallback value if doing so hides important failures. At a service boundary, you can translate the cause into a domain error while keeping the cause chain intact.

`submit(Runnable)` also returns a `Future<?>` and records any failure of the `Runnable` so `get()` reports it via `ExecutionException`; when the `Runnable` completes normally, `get()` typically returns `null` (or the `result` value supplied via the `submit(Runnable, result)` overload).

**Compared to `execute(Runnable)`**: `execute` does not return a `Future` for the caller to call `get()`. How errors are reported/exposed from a worker depends on the executor and uncaught-exception handling. Therefore, do not call `submit()` and ignore the `Future` if you need to know whether the task succeeded.

## 5. Standalone Runnable Example: Timeout Does Not Mean Task Cancellation

`FutureTimeoutDemo.java` uses a `CountDownLatch` to ensure the task cannot complete before the caller attempts to wait. This keeps the example independent of machine speed or `Thread.sleep(...)`.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch gate = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                gate.await();
                return "hoàn thành";
            });

            try {
                System.out.println(future.get(100, TimeUnit.MILLISECONDS));
            } catch (TimeoutException e) {
                System.out.println("Hết hạn chờ");
            }

            System.out.println("Đã xong? " + future.isDone());
            gate.countDown();
            System.out.println("Kết quả sau đó: " + future.get());
        } finally {
            gate.countDown();
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Output:

```text
Hết hạn chờ
Đã xong? false
Kết quả sau đó: hoàn thành
```

`TimeoutException` only ends the first **wait**. The Future may still be running; after opening `gate`, the subsequent `get()` call retrieves the result. On a timeout in a real application, choose an intentional handling strategy: continue doing other work and check again later; report the timeout to the caller while allowing the worker to keep running; or call `cancel(true)` if you genuinely want to request cancellation and the task supports interruption. Never treat a timeout as proof that the worker has stopped.

Avoid unbounded `get()` calls on latency-sensitive paths (such as HTTP request-handling threads) without a timeout plan, resource limits, and failure handling.

## 6. `InterruptedException`: The Caller Was Interrupted, Not `ExecutionException`

`get()` is an **interruptible** waiting operation. If the thread **calling `get()`** is interrupted while waiting, `get()` throws `InterruptedException`. This is a wait-control event; it does not prove that the Future's `Callable` threw an exception. Conversely, an `InterruptedException` thrown **inside the worker** that escapes `Callable.call()` is a task failure and will be observed as the cause of `ExecutionException` when the caller calls `get()`.

When the method signature allows it, the simplest approach is to **propagate** the checked exceptions:

```java
static <T> T await(Future<T> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
```

If you catch `InterruptedException` to convert it into an unchecked exception, you should typically **restore the interrupt flag** of the current thread so higher call layers do not lose the signal:

```java
try {
    return future.get();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Luồng chờ đã bị ngắt", e);
} catch (ExecutionException e) {
    throw new IllegalStateException("Tác vụ thất bại", e.getCause());
}
```

The snippet above is an illustrative method body returning the same type as `future.get()`. When cancelling the Future fits the business logic, the caller can **explicitly** call `future.cancel(true)` in the interrupted branch; an interrupted `get()` does not do this automatically.

Do not ignore `InterruptedException` with `catch (InterruptedException ignored) {}` and then continue waiting indefinitely. And do not confuse the two directions of interruption: calling `future.cancel(true)` typically requests interrupting the **worker thread** running the task, whereas `Thread.currentThread().interrupt()` affects the current **caller thread**.

## 7. `cancel(...)`, `CancellationException`, and Completion State

```java
boolean accepted = future.cancel(true);

try {
    Object value = future.get();
} catch (java.util.concurrent.CancellationException cancelled) {
    // Future was cancelled; do not handle as ExecutionException.
}
```

This is an illustrative usage snippet, not a standalone program. `cancel(true)` attempts to cancel and, if the task is running, permits requesting an interrupt on the worker; it **does not guarantee** that executing worker code will stop immediately, especially if the task ignores interruption. `cancel(false)` does not request interrupting a running worker. The returned boolean indicates whether the cancellation request succeeded according to the Future's state; it is not confirmation that the worker has finished cleaning up all resources.

After a successful cancellation, both `isCancelled()` and `isDone()` return `true`, and `get()` throws `CancellationException`. Similarly, if a task has failed, `isDone()` is still `true`. Therefore, you must **read the result or exception from `get()`** if you need to distinguish success from failure.

If a timeout leads to a cancellation request, use a pattern with a clear decision:

```java
try {
    return future.get(2, java.util.concurrent.TimeUnit.SECONDS);
} catch (java.util.concurrent.TimeoutException timeout) {
    future.cancel(true); // Request stop according to application policy.
    throw timeout;
}
```

This is also an illustrative method body; the enclosing method must declare or handle `InterruptedException`, `ExecutionException`, and `TimeoutException`, as well as have an appropriate return type.

## 8. Concurrency Pitfalls When Using `get()`

### 8.1. Deadlock/starvation when waiting on a subtask in the same small executor

A task running in an executor **with only one worker** that submits a subtask to the same executor and calls `get()` to wait for it occupies the only worker; the subtask has no thread available to run.

```java
// Illustrates the pitfall; DO NOT run this snippet as a real program.
ExecutorService one = Executors.newSingleThreadExecutor();
Future<String> outer = one.submit(() -> {
    Future<String> inner = one.submit(() -> "inner");
    return inner.get(); // Waits for a subtask that has no worker available to run.
});
System.out.println(outer.get()); // May wait indefinitely.
```

Avoid waiting on cross-dependencies inside a resource-constrained pool; instead, use non-blocking task composition, separate executors appropriately, or design the processing flow so it does not need to wait on work sitting in the same queue.

### 8.2. Checking `isDone()` before `get()` does not replace exception handling

Even when:

```java
if (future.isDone()) {
    // get() will not need to wait for completion,
    // but it can still throw ExecutionException or CancellationException.
    future.get();
}
```

`isDone()` does not tell you whether the outcome was good or bad. If there is contention with a `cancel()` call, the state can also change between the check and the `get()` call. Usually, calling `get()` directly inside `try/catch` or using a timeout approach is clearer.

### 8.3. Forgetting to retrieve the Future's result

For tasks submitted with `submit`, errors are stored in the Future; if `get()` is never called and there is no other observation mechanism, the system can miss failures. Collect Futures and inspect their completion status, or use an asynchronous handling mechanism with explicit error reporting.

### 8.4. Confusing `shutdown()` with `cancel()`

`executor.shutdown()` only rejects new tasks and gives already-accepted tasks a chance to finish. It **does not** automatically cancel all Futures and does not wait until all workers terminate. When you need to wait for an executor to close, use `awaitTermination(...)` with a timeout and an interruption strategy; when you need a stronger stop request, consider `shutdownNow()` together with task code that cooperatively handles interruption.

### 8.5. Misunderstanding cross-thread memory visibility

According to the memory model contract of `Future`, actions taken by the asynchronous task **happen-before** actions following the corresponding `Future.get()` in another thread. As a result, `get()` is an important synchronization point when consuming results and data published by the task. This rule does not mean all shared variables across the entire application automatically become thread-safe; independent concurrent accesses still require appropriate synchronization.

## 9. Quick Comparison with `CompletableFuture`

`CompletableFuture<T>` also implements `Future<T>`:

| Waiting method | When the async stage fails | When the caller thread is interrupted |
|---|---|---|
| `future.get()` | `ExecutionException` containing the original cause | May throw `InterruptedException` |
| `future.get(timeout, unit)` | `ExecutionException` containing the original cause | May throw `InterruptedException`; also `TimeoutException` |
| `completableFuture.join()` | Usually `CompletionException` (unchecked) containing the original cause | Does not declare `InterruptedException` |

If a `CompletableFuture` is cancelled, both `get()` and `join()` can throw `CancellationException` directly. `join()` is not a drop-in replacement for `get()` because error reporting and interruption handling differ. When coordinating multiple tasks in an asynchronous pipeline, combinators such as `thenApply`, `thenCompose`, `handle`, and `exceptionally` on `CompletableFuture` can reduce the need to block workers with `get()`; this is an additional design choice and does not change the error contract of `Future.get()`.

## 10. Error-Handling Decision Pattern and Checklist

A typical handling flow has four distinct branches:

```text
Call Future.get(timeout, unit)
    ├─ returns result        → use the completed result
    ├─ ExecutionException    → extract cause and classify task failure
    ├─ InterruptedException  → respect caller interruption; propagate or restore
    ├─ TimeoutException      → decide to keep waiting, report timeout, or cancel
    └─ CancellationException → handle cancellation as a separate state
```

Before shipping code that uses `Future` to production, verify:

- Tasks are submitted via `submit(...)` and the `Future` is retained to observe success or failure.
- The reader inspects `ExecutionException.getCause()` for the relevant error types and preserves the cause chain when translating errors.
- The caller has a timeout policy if it cannot wait indefinitely; timeouts are distinguished from cancellation.
- `InterruptedException` is not swallowed; it is propagated or the interrupt flag is restored when needed.
- There is no nested waiting in an executor that could starve workers; tasks support cancellation/interruption where needed.
- The executor is shut down; there is a plan to await termination or clean up resources according to the service lifecycle.

**Key takeaway:** `get()` is the point where both the result and exceptions of an asynchronous task are received. `ExecutionException` indicates **the worker failed** and `getCause()` explains the underlying error; `InterruptedException`, `TimeoutException`, and `CancellationException` describe three distinct conditions on the waiting side or cancellation state, each requiring its own handling according to application policy.
