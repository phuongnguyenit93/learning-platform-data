# Testing Exceptions via Future and CompletableFuture in Java

> **Scope:** Java Core → Exception → Testing. This lesson guides you through writing repeatable tests for asynchronous tasks: errors arising in a worker, how `Future.get()` wraps errors in `ExecutionException`, how `CompletableFuture.join()` uses `CompletionException`, and handling cancellation, timeout, interruption, and dependent stages. Standalone examples run on Java 17; JUnit 5 tests are clearly distinguished as requiring a library outside the JDK.

## 1. Why is testing asynchronous exceptions different from synchronous testing?

In synchronous code, exceptions are thrown directly on the test method's call stack:

~~~java
// JUnit 5 snippet:
assertThrows(IllegalArgumentException.class,
        () -> parseRequired("not-a-number"));
~~~

However, when a task is submitted to an `ExecutorService` or runs inside a `CompletableFuture`, an error can occur on a **different thread**. The test must identify **the channel the API uses to publish failures**. If you only wrap the task submission statement with `assertThrows`, the test will very likely miss the worker's error.

~~~java
// JUnit 5 snippet; pool is already available:
Future<Integer> task = pool.submit(() -> {
    throw new IllegalStateException("worker failed");
});

// Wrong target: submit normally returns a Future as usual.
// assertThrows(IllegalStateException.class, () -> pool.submit(...));

// Right target: read the task result via get().
ExecutionException wrapper =
        assertThrows(ExecutionException.class, task::get);
assertInstanceOf(IllegalStateException.class, wrapper.getCause());
~~~

An asynchronous exception test should verify **three layers**: (1) the *task* actually failed, (2) the *completion mechanism* reports the error according to contract, and (3) the *business cause* has the expected type, message/code, cause, and data state.

## 2. Orientation table: what to wait on and what to catch?

| API/execution path | How worker error surfaces to caller | Exception type tests usually catch | Next question |
|---|---|---|---|
| Calling `Runnable.run()` directly | Exception propagates up the same stack | Original error type | Does it actually use a new thread? |
| `new Thread(...).start()` | Does not automatically throw `run()` errors to caller | `UncaughtExceptionHandler` or custom channel | `join()` only waits; it does not throw worker errors |
| `ExecutorService.submit(Callable)` | Error is recorded in the `Future` | `ExecutionException` from `get()` | Does `getCause()` match the original error? |
| `ExecutorService.submit(Runnable)` | Future also holds the task error | `ExecutionException` | `Runnable` does not need to return a value |
| `CompletableFuture.supplyAsync(...)` | Future completes exceptionally | `CompletionException` from `join()`; `ExecutionException` from `get()` | How do the cause and dependent stages behave? |
| `CompletableFuture.failedFuture(ex)` | Future fails immediately without running a worker | `join()`/`get()` as above | Do not infer that a thread was created |
| `CompletableFuture.cancel(...)` | Future is marked canceled | `CancellationException` on the direct future | Did the actual work stop? |
| `get(timeout, unit)` on an incomplete future | Wait time expired | `TimeoutException` | The task might **still be running** |
| `get()` when the waiting thread is interrupted | Wait was interrupted | `InterruptedException` | Do not confuse with a computation error |

You need to distinguish the ***observation path*** from the ***error-causing path***. A test targets `get()`/`join()` to observe an error already held in the future. It does not prove that the exception propagates across two threads on its own.

## 3. Core rules of Future.get()

`Future<T>` represents a result that may not be ready yet. For a `Future` from `ExecutorService.submit()`, if `Callable.call()` or `Runnable.run()` throws an exception, the framework records the error. When the caller invokes `get()`:

- If the task succeeds, it returns the result. With `submit(Runnable)`, this is usually `null` unless a specific result was provided.
- If the task fails with an exception, `get()` throws **`ExecutionException`**. `getCause()` lets you inspect the original exception.
- If the `Future` was canceled, `get()` throws **`CancellationException`**; do not treat this as a normal `ExecutionException`.
- If the **waiting thread** is interrupted, `get()` may throw **`InterruptedException`**, regardless of the task's final outcome.
- With `get(timeout, unit)`, a task that does not finish in time may result in **`TimeoutException`**. A waiter timeout does not prove the task failed or terminated.

A good test does not just assert the wrapper:

~~~java
// JUnit 5; future obtained from pool.submit(...).
ExecutionException ex =
        assertThrows(ExecutionException.class, future::get);

Throwable root = ex.getCause();
assertInstanceOf(IllegalArgumentException.class, root);
assertEquals("invalid amount", root.getMessage());
~~~

Checking `cause` matters because all different task errors can reach the caller under the same `ExecutionException` class. In APIs with domain wrappers, you may need to check the cause chain according to the application's own contract, but you should not arbitrarily unwrap layers and discard useful context.

## 4. CompletableFuture.join() and get(): two ways to observe an error

`CompletableFuture<T>` is both a `Future<T>` and an implementation of `CompletionStage<T>`. There are two common ways to wait for the result:

- `join()` declares no checked exceptions. For normal exceptional completion, it throws `CompletionException` with a `cause` related to the computation error.
- `get()` follows the `Future` contract, declaring `ExecutionException` and `InterruptedException` in its signature; it can also be canceled with `CancellationException`.
- Both can report `CancellationException` **directly** if the `CompletableFuture` itself is canceled. You should not assume every error from `join()` is a `CompletionException`.
- `getNow(defaultValue)` returns the default value when incomplete, but it is **not** an error-hiding mechanism: if already completed exceptionally, it can still throw a completion-style exception.

Example using a pre-created cause:

~~~java
// Snippet that can be placed inside a Java method:
IllegalArgumentException original =
        new IllegalArgumentException("bad payload");

CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(original);

// join(): CompletionException
try {
    failed.join();
} catch (CompletionException ex) {
    assert ex.getCause() == original;
}

// get(): ExecutionException
try {
    failed.get();
} catch (ExecutionException ex) {
    assert ex.getCause() == original;
}
~~~

The snippet above requires `java.util.concurrent.*` imports and the enclosing method to declare `throws InterruptedException` or catch it accordingly; plain Java `assert` statements also depend on the `-ea` flag. The JUnit 5 tests below use `assertThrows` and `assertSame` explicitly without depending on `-ea`.

**Note:** For errors wrapped across multiple dependent stages, the number of `CompletionException` layers and exact propagation behavior may differ from the direct path. Prefer checking the guaranteed `cause`/exception type rather than assuming every stage returns the exact same wrapper object.

## 5. Standalone Java 17 program: Future and CompletableFuture errors

Save as **`FutureExceptionTestingDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureExceptionTestingDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> submitted = pool.submit(() -> {
                throw new IllegalArgumentException("invalid amount");
            });

            try {
                submitted.get();
            } catch (ExecutionException ex) {
                System.out.println("Future.get: "
                        + ex.getClass().getSimpleName());
                System.out.println("Future cause: "
                        + ex.getCause().getClass().getSimpleName()
                        + ": " + ex.getCause().getMessage());
            }

            IllegalStateException original =
                    new IllegalStateException("service unavailable");
            CompletableFuture<String> failed =
                    CompletableFuture.failedFuture(original);

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println("CF.join: "
                        + ex.getClass().getSimpleName());
                System.out.println("CF cause: "
                        + ex.getCause().getClass().getSimpleName()
                        + ": " + ex.getCause().getMessage());
            }

            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("CF.get: "
                        + ex.getClass().getSimpleName());
            }

            AtomicInteger transformCalls = new AtomicInteger();
            CompletableFuture<Integer> dependent =
                    failed.thenApply(value -> {
                        transformCalls.incrementAndGet();
                        return value.length();
                    });

            try {
                dependent.join();
            } catch (CompletionException ex) {
                System.out.println("dependent cause: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("transform calls: " + transformCalls.get());

            CompletableFuture<String> recovered =
                    failed.exceptionally(ex -> "fallback");
            System.out.println("recovered: " + recovered.join());
            System.out.println("source still exceptional: "
                    + failed.isCompletedExceptionally());

            CompletableFuture<String> cancelled = new CompletableFuture<>();
            cancelled.cancel(true);
            try {
                cancelled.join();
            } catch (CancellationException ex) {
                System.out.println("cancelled.join: "
                        + ex.getClass().getSimpleName());
            }

            CompletableFuture<String> neverCompleted =
                    new CompletableFuture<>();
            try {
                neverCompleted.get(0, TimeUnit.NANOSECONDS);
            } catch (TimeoutException ex) {
                System.out.println("pending.get: "
                        + ex.getClass().getSimpleName());
            } catch (ExecutionException ex) {
                throw new AssertionError("pending task did not run", ex);
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac FutureExceptionTestingDemo.java
java FutureExceptionTestingDemo
~~~

**Exact stdout:**

~~~text
Future.get: ExecutionException
Future cause: IllegalArgumentException: invalid amount
CF.join: CompletionException
CF cause: IllegalStateException: service unavailable
CF.get: ExecutionException
dependent cause: IllegalStateException
transform calls: 0
recovered: fallback
source still exceptional: true
cancelled.join: CancellationException
pending.get: TimeoutException
~~~

### Why is the output deterministic?

1. `submitted.get()` waits for the task in the executor to finish with a failure before printing; there is no need for `Thread.sleep()` to guess when the error happens.
2. `failedFuture(original)` completes exceptionally **as soon as it is created**, without needing a worker to execute. `join()` surfaces the error as `CompletionException`, whereas `get()` surfaces it as `ExecutionException`.
3. `thenApply` only runs on the success branch. Because the source already failed, `transformCalls` remains `0`; the dependent stage reports exceptional completion.
4. `exceptionally` creates a stage with a fallback result. `recovered.join()` returns `fallback`, yet **`failed` remains exceptional**.
5. The `cancelled` future is canceled directly, so `join()` throws `CancellationException` instead of a result.
6. `neverCompleted` has no producer; `get(0, NANOSECONDS)` checks the state immediately and throws `TimeoutException`. This test does not depend on machine speed, though it **does not prove that an actual operation ran past a deadline**.
7. `pool.shutdownNow()` cleans up the executor. In integration tests with tasks that do not honor interruption, you should add a shutdown timeout and check for resource leaks.

This program demonstrates the exception contract. It does not benchmark performance and does not test the side effects or transactions of a real worker.

## 6. assertThrows at the right layer to avoid false positives

A common mistake:

~~~java
// WRONG testing scope (JUnit 5, executor is already available).
assertThrows(IllegalStateException.class, () -> {
    pool.submit(() -> {
        throw new IllegalStateException("task failed");
    });
});
~~~

Calling `submit` usually only submits the work and returns a `Future`; the execution exception does not jump onto `assertThrows`'s stack. If the outer lambda happens to throw `IllegalStateException` due to another bug, the test could **pass for the wrong reason**.

Clearly separate the submission point from the observation point:

~~~java
Future<?> future = pool.submit(() -> {
    throw new IllegalStateException("task failed");
});

ExecutionException ex =
        assertThrows(ExecutionException.class, future::get);
assertInstanceOf(IllegalStateException.class, ex.getCause());
assertEquals("task failed", ex.getCause().getMessage());
~~~

Similarly with `CompletableFuture`:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid id"));

CompletionException ex =
        assertThrows(CompletionException.class, stage::join);
assertInstanceOf(IllegalArgumentException.class, ex.getCause());
~~~

When code returns a `CompletableFuture` that already failed during validation, the test still has to call `join()` or inspect the stage to see **exceptional completion**. It should not assume by default that the future-creating method throws synchronously, unless the **API contract** explicitly specifies fail-fast throwing.

## 7. Complete JUnit 5 test suite: the key contracts

Below is **a JUnit 5 test class** that requires `junit-jupiter` and the JUnit test engine in your project; JDK 17 does **not** bundle JUnit. Save it at the corresponding test path with the filename **`AsyncExceptionContractTest.java`**. The examples avoid thread sleep and verify both wrapper and cause.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(5)
class AsyncExceptionContractTest {
    private final ExecutorService pool =
            Executors.newSingleThreadExecutor();

    @AfterEach
    void cleanup() {
        pool.shutdownNow();
    }

    @Test
    void submitWrapsTaskFailureWithExecutionException() {
        Future<Integer> future = pool.submit((Callable<Integer>) () -> {
            throw new IllegalArgumentException("bad row");
        });

        ExecutionException ex =
                assertThrows(ExecutionException.class, future::get);
        assertInstanceOf(IllegalArgumentException.class, ex.getCause());
        assertEquals("bad row", ex.getCause().getMessage());
    }

    @Test
    void completableFutureJoinAndGetExposeDifferentWrappers() {
        IllegalStateException cause =
                new IllegalStateException("repository down");
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(cause);

        CompletionException fromJoin =
                assertThrows(CompletionException.class, failed::join);
        ExecutionException fromGet =
                assertThrows(ExecutionException.class, failed::get);

        assertSame(cause, fromJoin.getCause());
        assertSame(cause, fromGet.getCause());
    }

    @Test
    void failedSourceSkipsSuccessTransform() {
        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> derived =
                source.thenApply(value -> {
                    calls.incrementAndGet();
                    return value.length();
                });

        IllegalArgumentException cause =
                new IllegalArgumentException("invalid request");
        assertTrue(source.completeExceptionally(cause));

        CompletionException ex =
                assertThrows(CompletionException.class, derived::join);
        assertSame(cause, ex.getCause());
        assertEquals(0, calls.get());
    }

    @Test
    void exceptionallyRecoversOnlyDependentStage() {
        CompletableFuture<String> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("offline"));

        CompletableFuture<String> recovered =
                source.exceptionally(ex -> "fallback");

        assertEquals("fallback", recovered.join());
        assertTrue(source.isCompletedExceptionally());
        assertFalse(recovered.isCompletedExceptionally());
    }

    @Test
    void cancelledSourceThrowsCancellationDirectly() {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> derived =
                source.thenApply(String::length);

        assertTrue(source.cancel(true));
        assertTrue(source.isCancelled());
        assertTrue(source.isCompletedExceptionally());

        assertThrows(CancellationException.class, source::join);
        CompletionException ex =
                assertThrows(CompletionException.class, derived::join);
        assertInstanceOf(CancellationException.class, ex.getCause());
    }

    @Test
    void pendingGetTimesOutWithoutFailureCompletion() {
        CompletableFuture<String> pending = new CompletableFuture<>();

        assertThrows(TimeoutException.class,
                () -> pending.get(0, TimeUnit.NANOSECONDS));
        assertFalse(pending.isDone());

        assertTrue(pending.complete("ready"));
        assertEquals("ready", pending.join());
    }

    @Test
    void workerHasStartedBeforeItsFailureIsReleased()
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", ex);
                }
                throw new IllegalStateException("expected failure");
            });

            assertTrue(started.await(2, TimeUnit.SECONDS));
            assertFalse(future.isDone());

            release.countDown();
            ExecutionException ex =
                    assertThrows(ExecutionException.class, future::get);
            assertInstanceOf(IllegalStateException.class, ex.getCause());
            assertEquals("expected failure",
                    ex.getCause().getMessage());
        } finally {
            release.countDown();
        }
    }
}
~~~

### Takeaways from the test suite

- `assertThrows` is placed on the `future.get()` or `stage.join()` call, not on `submit` or `supplyAsync`.
- The `join` and `get` test uses **the exact same cause** to distinguish wrappers without making assumptions about scheduler outcomes.
- The dependent stage test confirms **the success-branch callback does not run** and the original cause is preserved.
- The `exceptionally` test confirms the **new** stage succeeds while the source stage remains failed; avoiding the misconception that recovery mutates the past.
- The cancellation test distinguishes `CancellationException` directly from the source versus the exception propagated through a derived stage.
- The timeout test uses a pending future with no producer; asserting `isDone()==false` proves a wait timeout **does not complete or cancel the future**.
- The `CountDownLatch` test coordinates state so we know the worker has started but has not yet been allowed to throw; no `Thread.sleep()` is needed. `@Timeout(5)` keeps the test from hanging indefinitely under abnormal conditions.
- `@AfterEach` stops the executor. In real tests, you may need to await termination with a bound or use appropriate teardown to ensure resources do not leak.

A bug in the `CountDownLatch` test could trigger the `IllegalStateException("interrupted", cause)` branch; the test expects `"expected failure"` to detect if the worker was interrupted before being released. This is why asserting only the exception type across all paths may not be enough.

## 8. Testing checked exceptions of Callable

`Callable<V>.call()` declares `throws Exception`; therefore, a task can throw `IOException` without needing to wrap it as unchecked at the execution site:

~~~java
// JUnit 5; pool is already initialized.
Future<String> future = pool.submit(() -> {
    throw new java.io.IOException("file unavailable");
});

ExecutionException ex =
        assertThrows(ExecutionException.class, future::get);
assertInstanceOf(java.io.IOException.class, ex.getCause());
assertEquals("file unavailable", ex.getCause().getMessage());
~~~

What needs to be verified is not "`Callable` throws a checked exception across threads." In reality, `submit` stores the `Throwable` raised by `call()`; `get()` on the caller throws an `ExecutionException` whose cause is `IOException`.

With `Runnable.run()`, the signature declares no checked exceptions; code inside `Runnable` must handle or wrap checked errors before letting the task terminate abnormally. Tests need to classify the exact wrapper created by the application.

## 9. Testing exceptions in a CompletableFuture chain

A chain has multiple points where it can fail:

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("12")
                .thenApply(Integer::parseInt)
                .thenApply(n -> n / 0);
~~~

This snippet **does not reach the final stage** if the parse stage fails; in this specific example, `"12"` parses successfully, and then dividing by zero in the next stage produces `ArithmeticException`. Tests should check the exact stage/cause:

~~~java
CompletionException ex =
        assertThrows(CompletionException.class, result::join);
assertInstanceOf(ArithmeticException.class, ex.getCause());
~~~

Key questions:

1. When an earlier stage fails, is a subsequent stage that only runs on the success branch skipped?
2. Do `thenApply`/`thenCompose` add wrappers or change the original cause according to contract?
3. Does `exceptionally` accidentally produce a fake success result?
4. Does `handle` return the proper fallback and avoid exposing `null`?
5. Is `whenComplete` used to **observe**, or did the author think it would recover? If the source fails, the stage returned by `whenComplete` usually still fails.
6. If a recovery callback throws a new error itself, the test should confirm the dependent stage reflects the **callback error**.
7. If a stage is canceled, does any consumer accidentally recover cancellation into a successful result?

Do not only test `source.isCompletedExceptionally()`; that does not tell you what the caller receives after composition. Test the **final stage exposed in the API** and important intermediate stages when they have their own contracts.

## 10. Testing failedFuture, completeExceptionally, and completion races

`CompletableFuture.failedFuture(cause)` creates a future that is immediately completed exceptionally, convenient for testing consumer logic without needing a real thread:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad id"));
~~~

`completeExceptionally(cause)` is used for an **existing** future. It returns a boolean indicating whether the call completed the pending future. Tests should verify that the first completion wins:

~~~java
CompletableFuture<String> promise = new CompletableFuture<>();
IllegalArgumentException cause =
        new IllegalArgumentException("bad input");

assertTrue(promise.completeExceptionally(cause));
assertFalse(promise.complete("late success"));
assertTrue(promise.isCompletedExceptionally());

CompletionException ex =
        assertThrows(CompletionException.class, promise::join);
assertSame(cause, ex.getCause());
~~~

Do not call `completeExceptionally` twice and expect the second call to overwrite the first. In a race between `complete`, `completeExceptionally`, and `cancel`, the winning state depends on execution order. If you want to test a race, use `CountDownLatch`/`CyclicBarrier` or a controlled executor, then assert **one valid outcome in the allowed set**, rather than hard-coding which thread wins.

Note that `CompletableFuture.cancel(boolean)` has its own boolean return semantics: an already-canceled future may continue returning `true` on subsequent `cancel` calls. Do not apply conclusions from `completeExceptionally` to `cancel` without reading the class contract.

## 11. CancellationException does not prove the worker stopped

`Future.cancel(true)` and `CompletableFuture.cancel(true)` have different characteristics:

- With `FutureTask` typically returned by `ExecutorService.submit`, `cancel(true)` can **request an interrupt** on the running worker. The task still has to cooperate to stop.
- With `CompletableFuture`, the `mayInterruptIfRunning` parameter is **not used to control the computation**; simply canceling the future does not prove the supplier was interrupted.
- `CancellationException` from `get()`/`join()` reports a canceled completion state, **not proof of transaction rollback**.
- If there were side effects before cancellation, those side effects may still persist.

In tests, separate:

1. **Future state:** `isCancelled()`, `isDone()`, `isCompletedExceptionally()`, and the exception when retrieving the result.
2. **Worker state:** did it receive the cancellation signal, does it check the flag/token, did it terminate?
3. **Business state:** does data preserve invariants, was it committed or not, is retrying safe?

A test that only runs `assertThrows(CancellationException.class, future::join)` proves neither of the latter two items. If your API requires actual cancellation, the test must observe the task via a latch, token, or properly synchronized state.

## 12. TimeoutException and time measurement

There are two distinct testing goals:

### Testing the timeout contract of get

Create an uncompleted future and call `get(0, TimeUnit.NANOSECONDS)`; we check for `TimeoutException` when no result is available yet. This is a **scheduler-independent** way to test the waiting contract.

### Testing a real deadline of a service

If you need to verify that the system times out after a deadline, the test should control time using a clock abstraction/test scheduler when the framework allows, or use a short bounded timeout and accept concurrency/integration conditions. Do not assert millisecond-level precision using only `System.currentTimeMillis()`, as the scheduler, GC, and machine load can cause drift.

**Very important:** `TimeoutException` from `Future.get(timeout)` **does not automatically complete the Future exceptionally**. It only indicates that the caller waited too long. Conversely, `CompletableFuture.orTimeout(...)` can complete the future itself with `TimeoutException` upon expiration; tests for the two APIs must differ.

To test `orTimeout` without relying on real wall-clock time, you can design a wrapper that accepts a fakeable scheduler/clock; the JDK's `CompletableFuture.orTimeout` does not provide direct clock injection. For integration tests using a real clock, always have an overall test timeout and clear cleanup.

## 13. Interrupts: do not confuse waiting-thread errors with task errors

`InterruptedException` from `Future.get()` is thrown on **the thread calling `get`** when that thread is interrupted while waiting. It is not the task's original exception.

A test can create a thread whose sole job is waiting:

~~~java
// Java snippet; waitingFuture is an uncompleted CompletableFuture.
Thread waiter = new Thread(() -> {
    try {
        Thread.currentThread().interrupt();
        waitingFuture.get();
        throw new AssertionError("expected interruption");
    } catch (InterruptedException expected) {
        Thread.currentThread().interrupt();
        // Record via AtomicBoolean/latch if the test needs to observe it.
    } catch (ExecutionException unexpected) {
        throw new AssertionError(unexpected);
    }
});
waiter.start();
waiter.join();
~~~

This example actively sets the interrupt flag on **the waiter itself** before `get()` and assumes the future is not yet complete. The code is just a snippet; a full test needs to assert the observation channel and ensure exceptions in the child thread are not missed.

When catching `InterruptedException` and unable to declare `throws` further, you should usually call `Thread.currentThread().interrupt()` to restore the flag and exit per cancellation policy. However, if a test needs to prove the flag was cleared when the blocking operation threw, measure it **before** re-interrupting; do not confuse the flag value after the catch block with the API's raw behavior.

Cancellation tests must also distinguish `CancellationException` (the future was canceled) from `InterruptedException` (the waiting thread was interrupted). They are not interchangeable.

## 14. Avoid Thread.sleep for coordinating tasks in tests

An unstable test is often written as:

~~~java
// Anti-pattern; reliability depends on machine load.
Future<?> future = pool.submit(this::doWork);
Thread.sleep(50);
assertTrue(future.isDone());
~~~

50 ms does not guarantee the worker has been scheduled or that I/O has finished. On an overloaded CI machine, the test fails randomly. Even increasing it to 500 ms only makes the test slower without providing a **synchronization relationship**.

Replace it with meaningful primitives:

- `Future.get()`: wait for completion and receive failures.
- `CountDownLatch`: signal "reached point X", "allowed to proceed".
- `CyclicBarrier` or `Phaser`: coordinate multiple participants when genuinely needed.
- `CompletableFuture`: create a controlled completion source via `complete`/`completeExceptionally`.
- `AtomicReference<Throwable>`/`AtomicBoolean`: store observations from another thread with proper memory visibility.
- `await(timeout, unit)` or a test-level timeout: protect the test from hanging forever if there is a bug.

Synchronization example:

~~~java
// Snippet; pool is already initialized.
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

try {
    Future<?> task = pool.submit(() -> {
        started.countDown();
        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("cancelled", ex);
        }
        throw new IllegalArgumentException("bad data");
    });

    if (!started.await(2, TimeUnit.SECONDS)) {
        throw new AssertionError("worker did not start");
    }
    release.countDown();

    ExecutionException ex =
            assertThrows(ExecutionException.class, task::get);
    assertInstanceOf(IllegalArgumentException.class, ex.getCause());
} finally {
    release.countDown();
}
~~~

This snippet requires importing the concurrent types and JUnit 5. Calling `release.countDown()` in `finally` prevents the worker from getting stuck if the test stops early. This is **event-based synchronization** rather than guessing timings.

## 15. Testing a worker without reading the Future's result can miss errors

`ExecutorService.submit()` records exceptions into the `Future`. If a test submits a task and finishes without calling `get()` or having a failure observation channel, it may **falsely pass** even though the worker threw an exception.

~~~java
// Insufficient if the goal is to verify the task's exception:
pool.submit(() -> {
    throw new IllegalStateException("unexpected failure");
});
// The test may finish here without asserting anything about the failure.
~~~

Proper approaches:

- Keep the `Future` and call `get()`, asserting `ExecutionException.getCause()`.
- If the API returns a `CompletableFuture`, attach a handler or `join()` the stage exposed to the caller.
- For fire-and-forget, design an error sink/uncaught handler or monitoring callback and test that exact channel.
- For a raw `Thread`, install an `UncaughtExceptionHandler` that writes the exception into an `AtomicReference`; `Thread.join()` only waits for the thread to finish and **does not rethrow the exception**.

Do not treat default stderr or uncaptured logs as automated proof that the test observed the failure. An automated test must assert a readable/controllable channel.

## 16. Testing exceptional completion does not automatically prove state rollback

If a task updates part of the data and then throws an error, the `Future` reports the failure accurately, but the data may be corrupted:

~~~java
// Code illustrating the risk, not a standalone program.
Future<?> future = pool.submit(() -> {
    accountA.debit(amount);
    failingOperation();
    accountB.credit(amount);
});
~~~

A test that only asserts `ExecutionException` only checks the **exception channel**, not the invariant "total balance remains unchanged." For business logic requiring atomicity, the test should:

1. Prepare a clear initial state.
2. Use fault injection to make the sensitive step throw an error.
3. Wait for the task to complete using `get()`/`join()`.
4. Verify the expected exception/cause.
5. Read the state through a proper synchronization channel and assert the invariant or strong exception guarantee per contract.
6. Verify external side effects outside the JVM, and retry/idempotency when interacting with DB/network.

A well-propagated asynchronous error does not by itself indicate that the operation rolled back. Neither `CompletableFuture.cancel(true)` nor `orTimeout(...)` automatically reverses side effects. Therefore, failure-notification testing and data-consistency testing must be **two independent groups of assertions**.

## 17. Common pitfalls

1. **`assertThrows` wrapping `submit` instead of `get()`:** task errors are transferred through the `Future`.
2. **Expecting `Thread.join()` to rethrow errors from `run()`:** `join` only waits for the thread to finish.
3. **Asserting only `ExecutionException`:** forgetting to check the cause and business message/code.
4. **Treating `CompletionException` and `ExecutionException` as identical:** they appear in different observation APIs.
5. **Assuming every `join()` failure is `CompletionException`:** direct cancellation can throw `CancellationException`.
6. **Asserting exceptions via regex on `getMessage()`:** messages are not machine-readable contracts; assert type/code/cause, and only assert message when it is a requirement of the test.
7. **Using `Thread.sleep` to wait for a worker:** prone to flakiness on CI or under a busy scheduler.
8. **Testing timeouts by sleeping for the exact deadline:** races and jitter can make tests unstable.
9. **Discarding the `Future` after `submit`:** task errors may go unseen by the test.
10. **Using `exceptionally` and thinking the source is no longer failed:** recovery creates a new dependent stage.
11. **Using `whenComplete` as if it always recovers errors:** it primarily observes; source errors usually still propagate.
12. **Testing `cancel` and inferring the thread stopped:** `CompletableFuture.cancel(true)` does not interrupt the supplier by contract.
13. **Swallowing `InterruptedException` in a test worker:** hides cancellation signals and makes teardown unreliable.
14. **Forgetting to shut down the executor:** tests leak threads or hang the test suite after assertions complete.
15. **Asserting only the exception, not the state:** missing rollback/invariant checks in code with side effects.
16. **Testing an incomplete stage with `get()` without a timeout:** the test can wait forever.
17. **Asserting the right cause on one stage but not on the final public stage:** real callers might receive a different wrapper/fallback.
18. **Using a single passing test run as proof of no race condition:** concurrency correctness requires reasoning about synchronization and multiple scenarios.

## 18. Checklist for building reliable tests

Before finishing an asynchronous exception test, ask yourself:

1. **What does the API return?** `Future`, `CompletableFuture`, `CompletionStage`, `Thread`, or a callback?
2. **On which stack does the error occur?** If inside a worker, the caller receives it via the completion API rather than catching it at `submit`.
3. **Where is the error observed?** `get()`, `join()`, handler, callback, or error sink.
4. **What is the expected wrapper?** `ExecutionException`, `CompletionException`, `CancellationException`, `InterruptedException`, or `TimeoutException`?
5. **Which cause matters?** Type, code, contracted message, business ID, and suppressed cause when needed.
6. **Are there dependent stages?** Verify that success callbacks do not run after failure and that recovery has the right scope.
7. **Is the incomplete state tested?** Do not wait forever; use a bounded timeout or deterministic control.
8. **Is the worker guaranteed to have started?** Use a latch/barrier instead of guessing with sleep.
9. **Does cancellation stop the real work?** Distinguish completion state from control signals and side effects.
10. **Are resources cleaned up?** Executors, latches, files, network connections, and data are reset in `finally`/teardown.
11. **Could the test miss a failure?** Discarded `Future`, unobserved callback, or thread exception only printed to stderr.
12. **After the error, do data invariants still hold?** Verify separately according to the business contract.

## 19. Summary

**Testing exceptions via Future and CompletableFuture** is about testing **the task's result channel**, not just the statement that creates or launches the task. With `Future.get()`, catch `ExecutionException` and inspect `getCause()`. With `CompletableFuture.join()`, catch `CompletionException` for normal exceptional completion and inspect the cause; distinguish direct cancellation with `CancellationException`. `CompletableFuture.get()` still follows the `Future` contract.

Also test dependent stages, fallbacks, cancellation, timeouts, interrupts, post-failure data state, and executor lifecycle. Use `CountDownLatch`/`Future.get()` instead of `Thread.sleep()` to control ordering and avoid flaky tests. Ultimately, a test is only valuable when it actually **observes the exception from the right channel** and verifies **the error type, cause, and state** that the caller receives.

### Official Java and JUnit references

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Java SE 17 — CancellationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [JUnit 5 — Assertions.assertThrows](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions)
