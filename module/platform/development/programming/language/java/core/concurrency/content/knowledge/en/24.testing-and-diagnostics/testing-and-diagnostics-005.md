# Testing Shutdown While Tasks Are Waiting or Running in Java Concurrency

## 1. Objectives and Scenarios to Prove

When a Java application uses an `ExecutorService`, stopping the executor may happen right while a task is **running**, **waiting on a resource**, or **queued but not yet started**. A test that merely calls `shutdown()` and checks `isShutdown()` does not prove that tasks are handled properly.

This lesson focuses on **testing the shutdown behavior of Java SE concurrency**, without relying on framework lifecycles. After this lesson, you will know how to:

1. Deterministically create a state with "one running task and one queued task".
2. Distinguish between an orderly shutdown (`shutdown()`) and an immediate stop request (`shutdownNow()`).
3. Verify whether accepted tasks complete or are cancelled/interrupted, whether new tasks are rejected, and whether the executor actually terminates.
4. Write tests that do not depend on the luck of `Thread.sleep()`, have timeouts, and always release threads after the test.

**Terminology to distinguish:** a "waiting task" can be either (a) a task that has **not yet run**, sitting in the work queue, or (b) a task that has **already started running but is blocked**, such as at `CountDownLatch.await()`, `BlockingQueue.take()`, or an I/O call. The two cases produce different results when `shutdownNow()` is called; the test must clearly specify which state is being verified.

## 2. Lifecycle Contract of `ExecutorService`

| Command / State | Meaning to Test |
|---|---|
| `shutdown()` | Stops accepting new tasks. Previously submitted tasks, including running and queued tasks, are allowed to continue until completion. The call **does not wait** for all tasks to finish. |
| `shutdownNow()` | Attempts to stop actively executing tasks (typically via `Thread.interrupt()`), halts the processing of waiting tasks, and returns a list of `Runnable`s that never commenced execution. This is **best effort**. |
| `isShutdown()` | Indicates that the executor has been requested to shut down; **does not mean** all workers have stopped. |
| `isTerminated()` | `true` when all tasks have completed **following** shutdown. |
| `awaitTermination(timeout, unit)` | Waits up to the specified timeout: returns `true` if the executor terminated, `false` if the timeout elapsed; may throw `InterruptedException`. |
| `submit(...)` after shutdown | Typically rejected with `RejectedExecutionException`; the implementation's `RejectedExecutionHandler` policy may affect how rejection is reported. |

Important notes:

- `shutdown()` **does not actively interrupt** running tasks. Nor does it automatically cancel every submitted `Future`.
- `shutdownNow()` is a **best-effort stop request**. A task that does not respond to interruption may keep running, causing `awaitTermination` to time out. The returned list only represents tasks that **had not started**, not tasks that were successfully stopped.
- `Future.cancel(true)` aims to cancel **a single** task and may send an interrupt to the worker running that task; `shutdownNow()` is an **executor-level** operation. They are not synonymous.
- In Java 17, `ExecutorService` must be closed explicitly with `shutdown`/`shutdownNow`; do not write `try-with-resources` for an `ExecutorService` variable when targeting JDK 17.
- `isTerminated() == false` immediately after `shutdown()` is usually normal. Only conclude that shutdown is complete after having the corresponding state evidence and completion signals.

## 3. Designing the Test Before Writing Code

Use **`Executors.newSingleThreadExecutor()`** for easy control: only one worker. Have task A signal "started", then wait on an unopened `CountDownLatch`. While task A still holds the worker, a submitted task B is guaranteed not to be able to start.

```text
Executor (1 worker)
          |
          +--> Task A: starts -> CountDownLatch.await() -> blocking
          |
          +--> Work queue: [ Task B ] -> not yet running

Test thread:
  1. Submit A; wait for A to signal it has started.
  2. Submit B while A is still blocked.
  3. Call shutdown() OR shutdownNow().
  4. Verify state, processing order, and cleanup.
```

`CountDownLatch` is a **deterministic synchronization point**, avoiding "sleep 100 ms and hope task A has reached the right place". Even so, all wait calls in a test should have a timeout so that synchronization bugs cause the test to **fail finitely** rather than hanging the entire test suite.

Expected behavior table:

| State at Shutdown Time | With `shutdown()` | With `shutdownNow()` |
|---|---|---|
| A has started, blocked at `await()` | A keeps waiting; once the latch opens, A can complete normally. | The executor attempts to interrupt A; if A is in an interruptible wait, `await()` throws `InterruptedException`. |
| B is in the queue, not yet running | B is still executed after A if A completes. | B typically appears in the list of unstarted tasks returned by `shutdownNow()`; B is no longer executed by the executor. |
| Task C submitted **after** shutdown | Not accepted under the normal rejection policy. | Not accepted under the normal rejection policy. |
| `awaitTermination` while A is still waiting | Returns `false` when the timeout elapses. | May return `false` if A has not responded to the interrupt or has not finished yet; returns `true` once all workers have stopped. |

Every assertion must be based on observable events: `Future.get(timeout)`, flag values, latches, the count of unstarted tasks, `isShutdown()`, `isTerminated()`, and the result of `awaitTermination`.

## 4. Complete Test Program, Runnable Directly with Java 17

The example below contains **two independent tests** in the same Java class:

- `testGracefulShutdown()`: A is blocked and B is waiting; `shutdown()` still allows both A and B to complete, while rejecting new tasks.
- `testImmediateShutdown()`: A is blocked at an interruptible operation and B is waiting; `shutdownNow()` requests interrupting A, retrieves the unstarted task B, and then the test cancels B's `Future` so callers waiting on `Future.get()` do not wait indefinitely.

File **`ShutdownLifecycleTest.java`**:

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownLifecycleTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void testGracefulShutdown() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> active = executor.submit(() -> {
                started.countDown();
                release.await(); // Task A is running but waiting on the latch
                return "ACTIVE_DONE";
            });

            check(started.await(2, TimeUnit.SECONDS),
                    "A did not start");

            // The single worker is busy with A: B only sits in the queue.
            Future<String> queued = executor.submit(
                    () -> "QUEUED_DONE");

            executor.shutdown();
            check(executor.isShutdown(), "Not shutdown");
            check(!executor.isTerminated(),
                    "Terminated while A is blocked");

            // Task A has not been released yet: the executor cannot terminate yet.
            check(!executor.awaitTermination(100, TimeUnit.MILLISECONDS),
                    "Unexpected termination");

            boolean rejected = false;
            try {
                executor.submit(() -> "NEW_TASK");
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            check(rejected, "Submission was not rejected");

            // Let A finish, then the worker proceeds to process B.
            release.countDown();
            check("ACTIVE_DONE".equals(
                    active.get(2, TimeUnit.SECONDS)),
                    "A did not finish");
            check("QUEUED_DONE".equals(
                    queued.get(2, TimeUnit.SECONDS)),
                    "B did not finish");

            check(executor.awaitTermination(2, TimeUnit.SECONDS),
                    "Executor did not terminate");
            check(executor.isTerminated(),
                    "isTerminated() is false");
            System.out.println("graceful: PASS");
        } finally {
            release.countDown(); // Do not leave A stuck if an assertion fails.
            executor.shutdownNow();
            executor.awaitTermination(2, TimeUnit.SECONDS);
        }
    }

    private static void testImmediateShutdown() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean queuedRan = new AtomicBoolean(false);

        try {
            Future<String> active = executor.submit(() -> {
                started.countDown();
                try {
                    release.await(); // Can be interrupted.
                    return "RELEASED";
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return "INTERRUPTED";
                }
            });

            check(started.await(2, TimeUnit.SECONDS),
                    "A did not start");

            Future<?> queued = executor.submit(
                    () -> queuedRan.set(true));

            // With the single worker still holding A, B cannot start yet.
            List<Runnable> neverStarted = executor.shutdownNow();

            check(executor.isShutdown(), "Not shutdown");
            check(neverStarted.size() == 1,
                    "Expected exactly one queued task");

            // Submitted tasks are typically wrapped in a FutureTask.
            // shutdownNow() returns unstarted tasks, but does not necessarily
            // mark their Futures as cancelled.
            for (Runnable task : neverStarted) {
                if (task instanceof Future<?> future) {
                    future.cancel(false);
                }
            }

            check("INTERRUPTED".equals(
                    active.get(2, TimeUnit.SECONDS)),
                    "A did not react to interrupt");
            check(queued.isCancelled(), "B future not cancelled");
            check(!queuedRan.get(), "B unexpectedly ran");

            check(executor.awaitTermination(2, TimeUnit.SECONDS),
                    "Executor did not terminate");
            check(executor.isTerminated(),
                    "isTerminated() is false");
            System.out.println("immediate: PASS");
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(2, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        testGracefulShutdown();
        testImmediateShutdown();
    }
}
```

Run on JDK 17 or later:

```bash
javac ShutdownLifecycleTest.java
java ShutdownLifecycleTest
```

Expected stdout when both tests pass:

```text
graceful: PASS
immediate: PASS
```

If an assertion fails, the program throws `AssertionError`; if a synchronization or completion milestone does not arrive within the allowed time, the test fails via `check(...)` or `Future.get(timeout)` with `TimeoutException`. The 2-second / 100-ms values are **bounds for the test environment**, not guarantees of JVM speed; when running on a heavily loaded CI machine, overall timeouts may need adjustment, but never replace them with a `sleep` that guesses state.

### Why Is This Test Deterministic?

1. `started.await(...)` confirms that A has entered the task body before submitting B.
2. There is only one worker, and A cannot exit `release.await()` unless released or interrupted. B therefore has no chance to start before the shutdown call.
3. For orderly shutdown, the test deliberately holds A unfinished to verify `awaitTermination(...)` returns `false`; it then releases A and waits for both `Future`s to return results.
4. For immediate shutdown, the test checks **A's interrupt response** and **that B did not run**, rather than assuming `shutdownNow()` must kill every thread instantaneously.
5. `finally` always opens the latch and requests executor shutdown, reducing the risk of a failed test leaving a non-daemon worker alive forever.

The example uses a single-thread executor with a default unbounded queue because the goal is **testing shutdown**, not measuring throughput or designing a production pool. If replaced with a `ThreadPoolExecutor` that has a custom `RejectedExecutionHandler`, a rejected submission may be represented differently; the test must match the executor's actual policy.

## 5. Analyzing Each Assertion: Do Not Confuse Requested State with Completed State

### `isShutdown()` Only Proves a Stop Was Requested

As soon as `shutdown()` returns, `isShutdown()` is `true`, but A is still blocked and B is still waiting. What additionally needs verification is that B actually runs after A and that `isTerminated()` eventually becomes `true`.

A test like the following is **insufficient**:

```java
executor.shutdown();
assert executor.isShutdown();
```

This is only an illustrative snippet, not a complete program. Even with Java assertions enabled via `-ea`, it proves neither cleanup nor task completion; testing the lifecycle requires `Future.get(timeout)` or `awaitTermination(...)`.

### `shutdownNow()` and the `Future` of Unstarted Tasks

In the example using `submit`, the executor may store `FutureTask` instances in the queue. `shutdownNow()` returns the list of **unstarted** `Runnable`s, but that does not mean every corresponding `Future` has transitioned to `isCancelled() == true`. If external code still holds a `Future`, define a policy for tasks drained from the queue: cancel the unstarted `Future`s, mark a failure state in the business system, or hand them off to another execution target (if the design allows). The example above explicitly calls `cancel(false)` so the `queued` state is finite.

**Do not use `neverStarted.size()` to claim how many running tasks were successfully interrupted.** It only counts tasks that had not started at the moment the queue was drained. Task A's response to interruption is checked separately via the result of `active.get(...)`.

### `InterruptedException` Is a Cooperative Signal

Java interruption **does not forcibly** terminate a thread. For interruptible waiting operations such as `CountDownLatch.await()`, the waiting thread will receive `InterruptedException`. For CPU-bound loops, the code usually needs to check the interrupt status itself:

```java
// Illustrative snippet inside a task, not a complete class.
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
// Exit the loop and clean up resources.
```

If a task catches `InterruptedException` and ignores it, continuing to wait indefinitely, `shutdownNow()` may be unable to make the executor terminate. When propagating an interrupt from a method that does not declare `throws InterruptedException`, it is common to call `Thread.currentThread().interrupt()` and exit in a controlled manner. Do not turn `Thread.stop()` into a shutdown solution: that method has been removed from safe practice because it can corrupt object invariants.

## 6. Testing When Tasks Wait on Locks, I/O, or Other Tasks' Results

`CountDownLatch` is an ideal test synchronization tool, but production tasks may wait on many different primitives:

| Where Is the Task Waiting? | Possible Reaction to Interrupt | How to Test |
|---|---|---|
| `CountDownLatch.await()`, `Thread.sleep()`, `BlockingQueue.take()` | Throws `InterruptedException` when interrupted (per API contract). | Use a latch to ensure it has entered the wait branch; assert the task records the interrupt and exits. |
| `ReentrantLock.lockInterruptibly()` | Can be interrupted while waiting for the lock. | Hold the lock on the test thread, have the worker signal readiness and then wait for the lock; interrupt and assert the exit path. |
| `synchronized` waiting for a monitor | `Thread.interrupt()` does not cause monitor entry waiting to throw `InterruptedException`. | The test must **release the monitor** so the worker can proceed; do not assume `shutdownNow` can terminate immediately. |
| CPU computation in a long loop | Does not automatically throw an exception on interrupt. | Have the task check `isInterrupted()` or an explicitly designed cancellation mechanism. |
| Blocking I/O | Reaction depends on the specific API, channel, and I/O mechanism in use. | Design resources with appropriate timeouts/closing; test based on the specific API, without assuming all I/O is interruptible like a latch. |
| `Future.get()` | May throw `InterruptedException` if the calling waiting thread is interrupted. | Avoid dependency cycles between tasks; require timeouts or explicit synchronization mechanisms. |

**Test each primitive differently.** For example, `Lock.lockInterruptibly()` and `synchronized` cannot be treated identically, even though both may manifest as a thread in a waiting state.

### When a Task Ignores Interrupts

If you want to verify that shutdown times out when a task is uncooperative, you can create a test task that only finishes when a latch is opened, while **recording but ignoring interrupts**. The test should:

1. Ensure the task has actually started before shutdown.
2. Call `shutdownNow()` and prove that `awaitTermination(shortTimeout)` returns `false`.
3. **Always open the latch in `finally`** so the task exits, then call `awaitTermination` again.

This is the kind of negative test that must have explicit cleanup: without the final release signal, a non-daemon thread can keep the JVM alive indefinitely after the test has already reported a failure.

## 7. Testing Race Conditions and Edge Cases

Shutdown tests usually should not cover only a single happy path. The following scenarios are well worth testing separately in a comprehensive suite:

### 7.1. Submitting a Task Near Shutdown Time

When one thread calls `submit` concurrently with another thread calling `shutdown`, you cannot rely solely on two statements being "close together" to assert that a task is definitely accepted or rejected. Tests should coordinate using barriers/latches to deterministically establish both orderings:

- **Submitted before shutdown:** the task is accepted and `shutdown()` does not drop it.
- **Shutdown completed before submit:** the new task is rejected according to the normal executor policy.
- **True race:** acceptance or rejection may depend on execution order; assert **valid invariants** (no double execution, no lost accepted results, no new tasks run after shutdown takes effect) rather than forcing a single random schedule.

### 7.2. Calling Shutdown Multiple Times

`shutdown()` and `shutdownNow()` are designed for the executor termination lifecycle, so tests can call them repeatedly to confirm no new tasks are accepted and no unintended side effects occur. Calling `shutdown()` after `shutdownNow()` does not "reopen" the executor. There is no API to restart a shut-down `ExecutorService`.

### 7.3. Task Throwing an Exception

A `submit`ted task may terminate with an exception. `Future.get()` then throws an `ExecutionException` wrapping the error. This does not mean the executor cannot terminate; tests should separate **task failure** from **executor full shutdown**. Do not just assert `isTerminated()` and ignore the `Future` result.

### 7.4. Cancelling via `Future.cancel(true)`

For a task blocked at an interruptible point, `cancel(true)` can cause `Future.isCancelled()` to become `true` and `Future.get()` to throw `CancellationException`. However, a `Future`'s cancelled state **is not proof that the worker has immediately stopped** if the task code does not cooperate. To prove cleanup, check signals from the task and when the executor terminates.

### 7.5. Tasks Stuck Due to Deadlock

If A holds a lock and waits for B's result, while B needs the very lock A holds, shutdown will not break the deadlock. A single-thread executor can also easily self-deadlock if task A waits on the `Future` of task B submitted to the same pool. Before blaming shutdown, check for dependency cycles, stack traces, and thread dumps. Tests with timeouts help detect the hang symptom; they do not automatically identify the root cause.

## 8. Organizing Tests in a Java Project

A good test should separate **arrange → act → assert → cleanup**:

```text
Arrange
    create an isolated executor for each test
    create a latch signaling the task has started
    hold task A at a deterministic wait point
    submit task B and establish that B has not started

Act
    call shutdown() or shutdownNow()

Assert
    confirm isShutdown()
    check Future results, rejected tasks,
    interrupt/cancel/queue behavior
    confirm awaitTermination(...) and isTerminated()

Cleanup (finally)
    open all remaining locked latches
    request shutdownNow() if needed
    awaitTermination(timeout) and report cleanup failure if it does not stop
```

When moving to JUnit, the two methods above can be split into independent test methods, using JUnit assertions and fixture cleanup in `@AfterEach`. The complete program in section 4 **has no dependency on JUnit or external libraries**, so it can be run directly with JDK 17.

### Testing Timeouts Responsibly

- **Short timeout for observation**: e.g. `awaitTermination(100, MILLISECONDS)` when you know for certain A is waiting on an unopened latch.
- **Wide enough timeout for valid events**: e.g. `Future.get(2, SECONDS)`, `started.await(2, SECONDS)`. Specific numbers depend on the environment and machine load.
- **Do not use delays to create ordering**: `Thread.sleep(100)` does not guarantee B has entered the queue or A has reached the wait point.
- **Do not make tests depend on the ordering of two unsynchronized tasks**: the order can change with multiple workers.
- **Do not ignore `InterruptedException` on the test thread**: if the test thread is interrupted while waiting, treat it as a test failure or propagate the exception; in complex cleanup logic it may be necessary to restore the interrupt flag per the framework's policy.

A particularly important principle is distinguishing **test timeouts** from **production system timeouts**. Tests are designed to finish finitely and surface bugs easily; production needs deadlines and graceful shutdown strategies suited to the level of data safety required.

## 9. Practical Shutdown Workflow and What to Verify

A common pattern when closing an executor in a Java program:

```java
// Illustrative snippet inside a method declaring throws InterruptedException.
executor.shutdown();
if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
        System.err.println("Executor still running");
    }
}
```

This snippet **is not a standalone runnable Java class**. It illustrates the sequence: stop accepting new work → wait for accepted work → request interruption if past the deadline → wait further and report if still not terminated. `shutdownNow()` does not replace per-task timeout/cancellation management, and how remaining tasks are handled must follow the application's data requirements.

In code that has a recovery policy when the calling thread is interrupted, it is common to need:

```java
// Illustrative snippet with an already-declared executor.
try {
    executor.shutdown();
    if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Restoring the interrupt flag notifies the caller that the current thread received an interrupt request. Do not catch `InterruptedException` and continue as if nothing happened.

In production, if there are tasks writing data, holding transactions, or owning I/O resources, you must determine **which work may be cancelled**, **which work must finish**, how to close resources, and how to handle pending requests. Those policies are independent of simply calling the two shutdown methods correctly.

## 10. Misleading Test Mistakes

| Incorrect Test Approach | Why It Is Wrong | Replace With |
|---|---|---|
| Call `shutdown()`; assert `isShutdown()`; consider it done. | The executor may still have A running and B waiting. | Wait on `Future` and `awaitTermination`, check tasks before/after shutdown. |
| Use `Thread.sleep(50)` to "ensure A starts". | Depends on the scheduler, CI machine, and timing. | `CountDownLatch` to signal the exact started milestone. |
| Use a 4-thread pool, submit only A and B, and claim B is queued. | B can run on the second worker. | A 1-worker pool, or ensure all workers are busy before submitting B. |
| Claim `shutdownNow()` stopped every task. | Interrupt is only a request; a task may not cooperate. | Verify task behavior, `Future` results, deadlines, and `isTerminated()`. |
| Call `Future.get()` without a timeout in a test. | A deadlock bug hangs the test suite forever. | Use `get(timeout, unit)` and cleanup in `finally`. |
| Fail to cancel `Future`s drained from the queue after `shutdownNow()`. | Holders of the `Future` may wait forever for a task that will never run. | Define and cancel/return status for unstarted tasks. |
| Forget to release the latch when an assertion fails. | Non-daemon threads can stay alive forever. | Release in `finally`, request shutdown, and check termination. |
| Only check that task B did not print a log. | Not printing a log does not prove the task did not run. | Use `AtomicBoolean`, `Future`, and the `neverStarted` list; establish synchronization relationships. |
| Use performance benchmark results to conclude shutdown is correct. | Benchmarks do not prove ordering and lifecycle. | Lifecycle tests with specific assertions; benchmarking is a separate problem. |

## 11. Practice Exercises

**Exercise 1 — graceful shutdown:** If task A holds the worker at `CountDownLatch.await()`, task B has been submitted, and `shutdown()` is called, what happens to task B? **Answer:** B remains in the valid queue. Once A is released and completes, the worker can execute B; only after all accepted tasks have finished does the executor terminate.

**Exercise 2 — immediate shutdown:** If A is blocked at `BlockingQueue.take()` and has code that catches `InterruptedException` and exits, does `shutdownNow()` guarantee that the executor is terminated *at the exact moment the method returns*? **No.** It requests interruption, but the worker still needs time to react and clean up. You must check `awaitTermination`.

**Exercise 3 — queued Future:** A task created by `submit()` is still in the queue when `shutdownNow()` drains it. Why might `Future.get()` keep waiting? Because draining the task from the queue **does not automatically guarantee** the `Future` is completed/cancelled. If your own code manages the lifecycle, actively handle unstarted `Future`s.

**Exercise 4 — robustness:** If `newSingleThreadExecutor()` is replaced with `newFixedThreadPool(3)`, what must be done to be certain B is in the queue at shutdown? **Answer:** keep all 3 workers busy on latches before submitting B, or use a custom executor that allows inspecting queue state. Do not rely on `sleep`.

**Exercise 5 — interrupt response:** Why shouldn't a test expect `shutdownNow()` to kill a task waiting on a `synchronized` monitor immediately? Because waiting on an intrinsic monitor **is not interruptible in the way `CountDownLatch.await()` or `lockInterruptibly()` works**. To terminate the task, you need to explicitly define the resource release mechanism and exit condition.

## 12. Checklist When Reviewing Shutdown Tests

- The test creates **running**, **blocked**, and **queued** states without relying on random scheduling.
- Assertions distinguish `shutdown()` from `shutdownNow()`, for both **accepted** tasks and **newly submitted** tasks.
- There is evidence of interruption or cancellation, rather than only checking `isShutdown()`.
- All wait operations have timeouts, and `finally` ensures waiting signals are opened and the executor is cleaned up.
- `Future`s of tasks not executed after `shutdownNow()` have a clear policy.
- Tests are independent, do not share mutable executors across tests, and do not leak threads.
- Tests run on a JDK supported by the project, such as Java 17+, with observable output and failure conditions.

**Conclusion:** A proper shutdown test must verify the *real lifecycle* of tasks before and after closing the executor: whether accepted tasks complete, whether waiting tasks respond properly to interruption, whether unstarted tasks are withheld, whether new tasks are rejected, and whether the pool actually terminates. `CountDownLatch`, `Future.get(timeout)`, `awaitTermination`, and cleanup in `finally` turn unpredictable races into controllable tests.

### Java SE 17 References

- [`ExecutorService`: shutdown, shutdownNow, awaitTermination](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [`ThreadPoolExecutor`: task management and worker state](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [`CountDownLatch`: synchronizing start/release points](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [`Future`: waiting, cancelling, result state](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [`Thread.interrupt()` and interrupted status](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
