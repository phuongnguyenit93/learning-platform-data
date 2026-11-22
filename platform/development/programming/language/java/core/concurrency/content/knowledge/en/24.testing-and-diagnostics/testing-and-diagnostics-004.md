# Testing Timeout, Interruption, and Cancellation in Java Concurrency

## 1. Lesson Objectives and Scope

A program may wait too long for a result, receive a cancellation request, or receive an interrupt signal from another thread. These situations **differ in meaning and API contract**, even though they all manifest as the caller not receiving the expected result.

After this lesson, you can:

- Distinguish **timeout** (waiting budget expired), **interruption** (thread interrupt signal), and **cancellation** (task cancellation request) from task success and failure.
- Write Java tests that control event ordering using `CountDownLatch`, without relying on `Thread.sleep` to guess scheduler behavior.
- Test `Future.get(timeout)`, `Future.cancel(false/true)`, `Thread.interrupt()`, and `CompletableFuture.cancel(true)`.
- Separately verify **the Future state** and **whether the worker actually terminated**, including cleanup after test failures.
- Design deadlines, handle `InterruptedException` properly, check executor termination, and reduce flaky tests.

The scope is **standard Java (Java 17+)**; Spring-specific task execution and transaction mechanisms are not covered.

## 2. How Do Timeout, Interruption, and Cancellation Differ?

**Timeout**: the waiter has exhausted its time budget without a result. For example, `future.get(100, TimeUnit.MILLISECONDS)` throws `TimeoutException` when not yet completed. This **only ends the wait**, and does not automatically stop the computation.

**Interruption**: `Thread.interrupt()` sends a signal to a thread. The signal is represented by the interrupt flag or by `InterruptedException` from interruptible blocking calls. This is a **cooperative** protocol: the thread must stop/clean up or propagate the signal according to its policy. There is no guarantee that every CPU or I/O operation will exit immediately.

**Cancellation**: a request to stop work or mark a result as no longer needed. A `Future` can transition to the cancelled state before the worker releases its resources; `cancel(true)` attempts to interrupt the worker, whereas `cancel(false)` does not request an interrupt.

| API | Observable Behavior | Does It Stop Running Work? |
|---|---|---|
| `Future.get(timeout, unit)` | Throws `TimeoutException` if the wait times out | No |
| `CountDownLatch.await(timeout, unit)` | Returns `false` if not enough signals are received; may also throw `InterruptedException` | No |
| `Thread.join(timeoutMillis)` | Returns after the thread finishes or the timeout expires; need to check `isAlive()` | No |
| `Thread.interrupt()` | Sets the interrupt flag; some blocking operations throw `InterruptedException` | Best effort, depends on the task |
| `Future.cancel(false)` | May mark the Future as cancelled | Does not interrupt the worker |
| `Future.cancel(true)` | May mark as cancelled and attempt to interrupt the worker | Best effort, depends on the task |
| `CompletableFuture.cancel(true)` | Completes the future with cancellation | `mayInterruptIfRunning` does not interrupt the computation |
| `CompletableFuture.orTimeout(...)` | Completes exceptionally with `TimeoutException` on expiration | Does not guarantee stopping the source task |
| `CompletableFuture.completeOnTimeout(...)` | Completes with a fallback result if timed out | Does not guarantee stopping the source task |
| `ExecutorService.shutdownNow()` | Attempts to interrupt running tasks, returns queued tasks that have not started | Does not guarantee all tasks have exited |

Therefore, each test should answer two separate questions: **what outcome the caller receives** and **what state the worker is in**.

`TimeoutException` from a deadline-bounded wait is not the same as `CancellationException` when retrieving the result of a cancelled Future. `ExecutionException` from `Future.get` wraps a task failure; `InterruptedException` notifies the **waiting** thread that it received an interruption.

### Two Lifetimes of the Same Task

Suppose a worker runs a slow I/O call while the calling thread executes:

```java
try {
    return future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    // Caller timed out.
    // The Callable may still be running on the worker.
    throw ex;
}
```

This is an illustrative snippet inside a method with a suitable `future`, an appropriate return type, and the necessary checked exception declarations/handling; it is not a standalone program.

After the caller throws `TimeoutException`, the worker can still complete an external state change. Thus, a timeout does not imply rollback or cancellation of side effects. If stopping is required, the caller must design a `cancel(true)` policy, resource timeouts, or a cancellation mechanism supported by the underlying API.

## 3. How to Write Reproducible Concurrency Tests

**Do not use sleep durations to prove ordering.** Calling `Thread.sleep(50)` in a test only delays the calling thread; it does not guarantee that the worker has started, acquired a lock, or reached the branch under test. CI machines, GC, and the scheduler can change the order.

Use synchronization checkpoints:

1. The worker calls `started.countDown()` right before the section being tested.
2. The test calls `started.await(3, SECONDS)` to know the worker has reached that checkpoint; use a timeout to protect the test from hanging.
3. The worker waits on `release.await()` so it does not run past the point the test wants to observe.
4. The test sends a cancel/interrupt signal or attempts to get the result with a timeout.
5. The worker calls `finished.countDown()` in `finally`; the test awaits this checkpoint to verify the work has left execution.
6. Cleanup in `finally` always releases latches and shuts down the executor; then verify executor termination.

`CountDownLatch` is a one-shot synchronization aid. If multiple rounds with multiple participants are needed, `CyclicBarrier` or `Phaser` may be more appropriate. For single-task tests, a latch is usually clear enough.

A good test uses timeouts **as a safety valve**, not to assert "must run in exactly 10 ms". When verifying that a wait times out, hold the task on a closed latch and wait with a clear timeout. The blocked condition is what produces the outcome, while the short timeout is merely the observation window.

## 4. Runnable Java 17 Test Program

This example covers five scenarios using standard Java: timeout without cancelling the task, cancelling a queued task, cancelling a running task with interrupt, direct interruption, and `CompletableFuture` cancellation.

Create the file **`LifecycleTests.java`**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class LifecycleTests {
    public static void main(String[] args) throws Exception {
        testTimeoutDoesNotCancel();
        testQueuedCancellation();
        testRunningCancellation();
        testDirectInterruption();
        testCompletableFutureCancellation();
        System.out.println("ALL TESTS PASSED");
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void await(CountDownLatch latch, String stage)
            throws InterruptedException {
        check(latch.await(3, TimeUnit.SECONDS), "Wait timed out: " + stage);
    }

    static void stop(ExecutorService executor) throws InterruptedException {
        executor.shutdownNow();
        check(executor.awaitTermination(3, TimeUnit.SECONDS),
                "Executor failed to terminate");
    }

    static void testTimeoutDoesNotCancel() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<String> task = executor.submit(() -> {
                started.countDown();
                release.await();
                return "done";
            });
            await(started, "timeout worker started");

            boolean timeout = false;
            try {
                task.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timeout = true;
            }
            check(timeout, "Expected get timeout");
            check(!task.isDone(), "Timed get must not finish task");

            release.countDown();
            check("done".equals(task.get(3, TimeUnit.SECONDS)),
                    "Worker should complete after release");
            System.out.println("PASS timeout");
        } finally {
            release.countDown();
            stop(executor);
        }
    }

    static void testQueuedCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);
        try {
            Future<?> first = executor.submit(() -> {
                firstStarted.countDown();
                release.await();
                return null;
            });
            await(firstStarted, "first task started");

            Future<?> second = executor.submit(() -> {
                secondRan.set(true);
                return null;
            });
            check(second.cancel(false), "Cannot cancel queued task");
            check(second.isCancelled(), "Task not marked cancelled");

            release.countDown();
            first.get(3, TimeUnit.SECONDS);
            try {
                second.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException expected) {
                // No result is available from cancelled task.
            }
            check(!secondRan.get(), "Cancelled queued task ran");
            System.out.println("PASS queued cancellation");
        } finally {
            release.countDown();
            stop(executor);
        }
    }

    static void testRunningCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch interrupted = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            Future<?> task = executor.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(TimeUnit.MINUTES.toMillis(10));
                } catch (InterruptedException ex) {
                    interrupted.countDown();
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
            await(started, "running task started");
            check(task.cancel(true), "Cancellation failed");
            check(task.isCancelled(), "Task not marked cancelled");

            // isCancelled() alone does not prove worker has stopped.
            await(interrupted, "worker received interrupt");
            await(finished, "worker finally finished");
            try {
                task.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException expected) {
                // Future result has been cancelled.
            }
            System.out.println("PASS running cancellation");
        } finally {
            stop(executor);
        }
    }

    static void testDirectInterruption() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch handled = new CountDownLatch(1);
        AtomicBoolean restored = new AtomicBoolean(false);
        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                Thread.sleep(TimeUnit.MINUTES.toMillis(10));
            } catch (InterruptedException expected) {
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            } finally {
                handled.countDown();
            }
        }, "interrupt-test");
        worker.start();
        try {
            await(started, "thread started");
            worker.interrupt();
            await(handled, "thread handled interrupt");
            worker.join(3_000);
            check(!worker.isAlive(), "Interrupted thread still alive");
            check(restored.get(), "Interrupted flag not restored");
            System.out.println("PASS direct interruption");
        } finally {
            worker.interrupt();
            worker.join(3_000);
        }
    }

    static void testCompletableFutureCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        try {
            CompletableFuture<String> task =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "done";
                        } catch (InterruptedException ex) {
                            interrupted.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            finished.countDown();
                        }
                    }, executor);
            await(started, "CompletableFuture worker started");
            check(task.cancel(true), "CompletableFuture cancel failed");
            check(task.isCancelled(), "Future not marked cancelled");
            check(finished.getCount() == 1,
                    "Underlying work unexpectedly finished");

            release.countDown();
            await(finished, "underlying work finished");
            check(!interrupted.get(),
                    "CompletableFuture cancel should not interrupt worker");
            try {
                task.join();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException expected) {
                // Cancellation is visible to future consumers.
            }
            System.out.println("PASS CompletableFuture cancellation");
        } finally {
            release.countDown();
            stop(executor);
        }
    }
}
```

Compile and run:

```bash
javac LifecycleTests.java
java LifecycleTests
```

Expected output:

```text
PASS timeout
PASS queued cancellation
PASS running cancellation
PASS direct interruption
PASS CompletableFuture cancellation
ALL TESTS PASSED
```

### Explanation of Each Test

**Timeout:** the worker can only return `"done"` after `release` is opened. When the test calls `get(100, MILLISECONDS)`, the task is still held at the latch; we verify `TimeoutException` and `!isDone()`, then open the latch and retrieve the result successfully. This is direct evidence that **a wait call's timeout does not cancel the task**.

**Cancel before running:** the single-thread executor is running the blocker; the second task sits in the queue. `cancel(false)` marks the unstarted task as cancelled. After releasing the blocker, the test verifies the second lambda was not executed. Note that `cancel(false)` on a **running** task may still change the Future's state depending on the implementation, but it does not request interrupting the worker.

**Cancel a running task:** the test awaits `started`, then calls `cancel(true)`. The worker in `Thread.sleep` can receive `InterruptedException` even if the interrupt arrives before calling `sleep`. In addition to `task.isCancelled()`, the test awaits `interrupted` and `finished`; this verifies that the worker went through both the interrupt-handling code and `finally`.

**Direct interrupt:** `worker.interrupt()` is a thread-level signal and does not require a Future. When `Thread.sleep` throws `InterruptedException`, the interrupt flag is cleared; the worker explicitly restores the flag via `Thread.currentThread().interrupt()`. The test records that in an `AtomicBoolean` and checks that the worker has terminated.

**CompletableFuture:** in Java 17, `CompletableFuture.cancel(true)` has the same parameter signature as `Future`, but the `mayInterruptIfRunning` parameter **is not used to interrupt the computation**. The test holds the work at `release.await()` in a separate executor, cancels the future, and then opens the latch itself. The task continues and finishes; the future's outcome remains cancelled.

Note: the 3-second bounded waits are *safety timeouts*. If a CI machine is overloaded, a test can fail due to the protective deadline; increase the timeout reasonably for the environment, but do not replace latches with sleeps. The test suite verifies specific controlled interleavings, not algorithm correctness across all execution schedules.

## 5. Handling Interruption According to Contract

### Reading and Restoring the Interrupt Flag

- `thread.isInterrupted()` reads the flag **without clearing** it.
- `Thread.interrupted()` (static) reads **and clears** the interrupt flag of the **current thread**, even when invoked via instance syntax.
- When blocking APIs such as `Thread.sleep`, `Object.wait`, `CountDownLatch.await`, `BlockingQueue.take`, or `Future.get` throw `InterruptedException`, the flag has already been cleared per the API contract.
- If a method allows `throws InterruptedException`, usually propagate the exception. If caught at an outer layer that cannot propagate it, usually restore the flag and terminate or follow the appropriate cancellation path; do not swallow the signal and continue running as if nothing happened.

Example of a callable with interruption checkpoints (illustrative snippet requiring `import java.util.concurrent.Callable;`):

```java
Callable<Long> work = () -> {
    long processed = 0;
    try {
        while (!Thread.currentThread().isInterrupted()) {
            Thread.sleep(100); // Replace with an actual interruptible operation.
            processed++;
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Stop the loop; handle partial results according to application policy.
    }
    return processed;
};
```

This snippet illustrates the cancellation protocol, **not** a complete business worker. A task returning partial results after an interrupt is only valid if the API accepts partial results; otherwise, propagate an error or represent the cancelled state explicitly.

### CPU-Bound Computation Tasks

`cancel(true)` does not automatically generate `InterruptedException` from arithmetic operations. Long-running computation tasks need to check the flag periodically:

```java
// Illustrative snippet inside a method that throws InterruptedException.
for (long i = 0; i < totalSteps; i++) {
    if (Thread.currentThread().isInterrupted()) {
        throw new InterruptedException("Requested to stop");
    }
    // Compute one step; totalSteps must be defined in an enclosing scope.
}
```

It is not necessary to check on every single iteration if the cost is too high; however, the check interval must be frequent enough relative to the target cancellation latency. Different blocking APIs may respond to interruption differently; check the documentation of the API/driver in use rather than assuming all I/O is interruptible.

Do not use `Thread.stop()` for "forced cancellation": this API is unsafe and deprecated, and can corrupt invariants of shared data.

### Is Lock Acquisition Interruptible?

When a thread waits to enter a `synchronized` monitor, `interrupt()` does not immediately wake it from waiting to acquire the monitor. With `ReentrantLock.lockInterruptibly()` or `tryLock(timeout, unit)`, the thread can receive `InterruptedException` or time out while waiting for the lock. Test the exact primitive that production actually uses.

## 6. Writing Timeouts at Deadlines, Not Just at `get` Calls

When the caller times out and the task is no longer useful, cancellation may be requested:

```java
// Illustrative snippet in a method with appropriate checked exception declarations.
Future<Result> future = executor.submit(() -> doWork());
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true); // Best effort; the worker may not stop immediately.
    throw timeout;
}
```

`Result`, `executor`, and `doWork` are illustrative names only, not a standalone program. If the caller receives `InterruptedException`, it must decide whether to request task cancellation and then propagate the signal, rather than silently ignoring the interruption. For irreversible side effects, determine the true outcome of the task before retrying.

An **overall deadline** avoids the case where a request calls three steps and each step is given a full 2 seconds (totaling up to 6 seconds). Use a monotonic clock to measure elapsed time:

```java
// Illustrative snippet inside a method that throws TimeoutException.
long startNanos = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(2);

// After a time-consuming step:
long remaining = budgetNanos - (System.nanoTime() - startNanos);
if (remaining <= 0) {
    throw new TimeoutException("Overall deadline exceeded");
}
// Pass remaining to the next timeout-aware wait step.
```

`System.nanoTime()` is meant for measuring elapsed intervals, not representing wall-clock date/time. Subtraction works for intervals smaller than the `long` representation range; guard against overflow when accepting arbitrary durations.

### Timeouts with Distinct Semantics

- `Thread.join(millis)` may return when expired while the thread is still alive. Tests must check `isAlive()` and have a cleanup path.
- `CountDownLatch.await(timeout, unit)` returns `false` if not enough signals arrived; it does not interrupt tasks on the other side.
- `Lock.tryLock(timeout, unit)` can return `false` due to failing to acquire the lock, or throw `InterruptedException`; these are two distinct cases.
- `CompletableFuture.orTimeout` completes the future exceptionally when expired; `completeOnTimeout` sets a fallback result. Neither guarantees the worker actually stops.
- `ExecutorService.awaitTermination(timeout, unit)` returns `false` when the executor has not finished; it does not call `shutdownNow()` again on its own.
- HTTP, socket, JDBC, or filesystem timeouts depend on the API; a Java wait timeout does not automatically trigger a transaction rollback or close resources of the underlying call.

## 7. Matrix of Scenarios to Test

| Scenario | How to Set Up State Before Trigger | Key Assertions |
|---|---|---|
| Timeout waiting for result | Worker held at `release.await()` | `TimeoutException`, `!future.isDone()`, still completes after release |
| Cancel queued task | Single-thread executor occupied by first task | Second task does not run, `isCancelled()`, `get()` throws `CancellationException` |
| Cancel running task | Worker signals `started` before interruptible wait | `cancel(true)`, `InterruptedException`, `finally` completes |
| Direct interrupt | Thread has entered wait region | Worker handles interruption, restores/propagates signal, terminates |
| Cancel non-cooperative CPU work | Task does not check interrupt flag | Do not assume `cancel(true)` stops the task; evaluate adding cancellation checkpoints |
| CompletableFuture cancel | Computation held by latch in separate executor | Future is cancelled, but computation is not interrupted by cancel |
| Failure other than cancellation | Callable intentionally throws an error | `Future.get()` throws `ExecutionException`; other tasks are not automatically cancelled |
| Timeout racing with interrupt | Two signals may occur close together | Accept outcomes allowed by API, do not infer an unsynchronized ordering |
| Cleanup after assertion failure | Latch still closed when test throws | `finally` always releases, shuts down, confirms termination with timeout |
| Executor does not stop | Worker ignores cancel or waits on non-interruptible API | `awaitTermination` returns false; explicitly report worker is still alive |
| Overall deadline | Multiple sequential wait operations | All steps use **remaining time budget**, do not reset timeout per step |

### Competing Signals

When `cancel`, `interrupt`, and timeout occur close together, the scheduler can cause threads to observe events in different orders. A test for **a specific branch** must control ordering with latches/barriers. A test for **a real race** should check the set of permitted outcomes and final invariants; do not assert a single execution schedule without a deterministic happens-before relationship.

## 8. Applying in JUnit 5 When the Project Has a Test Framework

Using JUnit Jupiter, you can replace `check` calls with `assertTrue`, `assertFalse`, `assertThrows`, and `assertEquals`. The following example is an **illustrative method**, requiring JUnit 5 and `java.util.concurrent` imports along with test class annotations:

```java
@Test
void timedGetDoesNotCancelRunningTask() throws Exception {
    ExecutorService pool = Executors.newSingleThreadExecutor();
    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    try {
        Future<String> future = pool.submit(() -> {
            started.countDown();
            release.await();
            return "ok";
        });
        assertTrue(started.await(3, TimeUnit.SECONDS));
        assertThrows(TimeoutException.class,
                () -> future.get(100, TimeUnit.MILLISECONDS));
        assertFalse(future.isDone());

        release.countDown();
        assertEquals("ok", future.get(3, TimeUnit.SECONDS));
    } finally {
        release.countDown();
        pool.shutdownNow();
        assertTrue(pool.awaitTermination(3, TimeUnit.SECONDS));
    }
}
```

Distinguish between JUnit's two timeout assertions:

- `assertTimeout(Duration, executable)` runs the executable and then evaluates the elapsed time; it is not used to stop the task when it exceeds the limit.
- `assertTimeoutPreemptively(Duration, executable)` runs the executable on a different thread and attempts to interrupt that thread on timeout; it does not guarantee non-cooperative work will stop. Thread-local context and side-effecting tasks may also continue unexpectedly.

For concurrency tests, checking **outcome + signal + cleanup** usually provides more useful diagnostics than wrapping a block in an assert-timeout alone. A test-runner framework-level timeout is also different from the timeout of the method under test.

## 9. Diagnosing Hung and Flaky Tests

**If it only times out in CI:** check whether the test is waiting on the `started` checkpoint, the `finished` checkpoint, or the `Future.get` result; log checkpoint names and adjust safety budgets for CI. Do not use `Thread.sleep` to "fix" ordering bugs.

**If `isCancelled` is true but execution has not exited:** the task may not have received the interrupt, may not be blocked on an interruptible API, or may be swallowing `InterruptedException`. Use a latch in `finally` to verify. `Future.isDone()` can also become true due to an exception before all application resources are closed.

**If the JVM does not exit after the test:** there is a remaining non-daemon executor thread, an unreleased latch, a task still waiting on a lock/I/O, or `shutdown()` was called without interrupting blocked tasks. Clean up in order: release all test-controlled latches, call `shutdownNow()` if policy permits, call bounded `awaitTermination`, and treat `false` as an explicit failure.

**If results vary across schedules:** check whether the test assumes `submit` means "task has run", `cancel` means "worker has finished", or uses log line order as proof. Add synchronization checkpoints and verify final invariants.

**If a failure looks like a timeout but is actually an interrupt:** `InterruptedException` indicates the waiting test thread was interrupted; check who called `interrupt`, and avoid accidentally clearing the flag with `Thread.interrupted()` in a helper.

You can use thread dumps / JDK diagnostics to identify threads in WAITING/BLOCKED/RUNNABLE states and their stack traces. Observing thread states is only a snapshot; correlate it with locks, queues, and synchronization points in the test.

## 10. Common Pitfalls and Review Checklist

1. **Timeout = cancel?** False. `get(timeout)` does not automatically cancel the task; after a timeout, consider `cancel(true)` based on business semantics.
2. **`cancel(true)` always kills the worker?** False. Interruption is cooperative; some APIs do not respond to interrupts or code ignores the interrupt flag.
3. **`cancel(false)` always fails if the task is running?** Do not assume this. Depending on the `Future` implementation, a task may be marked cancelled while still running; the API does not request an interrupt in this case.
4. **`CompletableFuture.cancel(true)` is the same as `FutureTask.cancel(true)`?** False. For `CompletableFuture`, the parameter behaves differently: it does not interrupt the computation.
5. **Swallowing `InterruptedException` is fine?** False. If the caller needs to know work was interrupted, propagate the signal/restore the flag and exit per contract.
6. **`Thread.interrupted()` only reads the flag?** False. It clears the current thread's flag; `isInterrupted()` is the non-clearing read.
7. **`Thread.sleep` helps tests determine ordering?** False. Use `CountDownLatch` or an appropriate synchronization primitive.
8. **`isDone()` proves the worker has cleaned up?** False. A cancelled `Future` can already be done in terms of state while the worker is still running.
9. **`shutdown()` guarantees stopping all tasks?** False. It does not interrupt already-running tasks; use `awaitTermination` and an appropriate cleanup policy.
10. **Retrying after a timeout is always safe?** False. Background work may have produced side effects before the caller lost the result; design idempotency or reconciliation if needed.

When reviewing a test, clearly identify: which actor sends the signal, which checkpoint the worker is guaranteed to have reached, which expectations belong to the API contract, which outcomes are permitted if a race occurs, and whether all workers are terminated on both pass and fail paths.

## Conclusion

**Timeout limits waiting time; interruption requests thread cooperation; cancellation marks/cancels the result and may send an interruption depending on the API.** Good tests separately verify the caller's outcome, the worker's reaction, and resource release. Use latches for controlled ordering, bounded waits to protect the test suite, and real state checks rather than relying on `sleep` or `isDone()` alone.