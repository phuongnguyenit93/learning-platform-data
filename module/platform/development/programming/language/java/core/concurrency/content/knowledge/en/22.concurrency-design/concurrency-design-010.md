# Timeout Budget Across Multiple Processing Steps in Java Concurrency

## 1. The problem: multiple steps sharing a single time budget

A concurrent task typically involves more than a single waiting operation. For example: fetch data from source A → fetch data from source B → wait for processing results on a thread pool → write the result. If each step is granted an independent 400 ms timeout, the total time can approach 1,600 ms, not counting queuing, retries, and intermediate processing. This violates the task's requirements if the caller only accepts at most 400 ms for the **entire** job.

A **timeout budget** is the maximum amount of time still allowed for the entire task. When multiple steps share a budget, the time spent in earlier steps must be subtracted from the time allowed for waiting in later steps.

Suppose the global budget is 400 ms:

| Event | Elapsed time | Remaining time |
| --- | ---: | ---: |
| Task starts | 0 ms | 400 ms |
| Step A completes | 120 ms | 280 ms |
| Step B completes | 270 ms | 130 ms |
| Step C wants to wait up to 180 ms | 270 ms | Allowed to wait at most 130 ms |
| Budget exhausted | 400 ms | 0 ms |

These numbers are illustrative; scheduling and task cancellation overhead may cause the observed completion time to slightly exceed the mark. A budget helps limit **the time allowed for waiting and starting subsequent work**, but does not automatically guarantee that every thread or I/O operation stops at the exact final millisecond.

The scope of this article is **general Java** concurrency mechanisms: threads, executors, `Future`, `CompletionStage`, locks, queues, and blocking calls. Spring-specific timeout configuration mechanisms belong to a separate chapter.

## 2. Distinguishing three concepts

- **Single-operation timeout**: the maximum time allocated specifically to the waiting call itself, such as `Future.get(timeout, unit)` or `Lock.tryLock(timeout, unit)`.
- **Task-wide budget**: the total time limit from when the task starts until it finishes. This includes CPU time, queuing, lock waiting, I/O, backoff, and retries.
- **Deadline**: the point in time when the budget expires on the clock used to measure elapsed time. Each step recalculates the remaining time from the **same deadline**, rather than initializing a new full timeout.

The invariant principle is:

> remaining = max(0, budget - elapsed); the timeout of the next step must not exceed remaining.

If a step has its own limit smaller than the shared budget, use `min(remaining, stepLimit)`. A step-specific limit only **narrows** the time for that step; it never grants extra time to the task.

Two concerns must be separated: (1) the caller **stops waiting** after expiration; (2) the running work **actually stops**. `Future.get` with a timeout solves (1); achieving (2) also requires cancellation, interruption, or timeouts specific to the underlying resource.

## 3. Choosing a clock: System.nanoTime instead of a wall-clock

To measure elapsed time **within the same JVM**, use `System.nanoTime()`. It is designed for measuring time intervals and is not tied to absolute date and time. `System.currentTimeMillis()` is a wall-clock; users, NTP, or the operating system can adjust it, skewing budget measurements.

Record:

- `startNanos = System.nanoTime()` right at the task start boundary.
- `elapsedNanos = System.nanoTime() - startNanos`.
- `remainingNanos = max(0, budgetNanos - elapsedNanos)`.

Do not directly compare a `nanoTime` value with a Unix timestamp. `nanoTime` has an arbitrary JVM origin; only **the difference between two readings from the same clock source** is meaningful. Subtraction on `long` integers allows counting across wrap-around for intervals smaller than $2^{63}$ nanoseconds (approximately 292 years), longer than any practical timeout.

Prefer nanoseconds for internal calculations and only convert to the unit required by an API when calling it. Converting to milliseconds via integer division can turn a very small positive duration into 0. In particular, **Thread.join(0)** means waiting indefinitely, so never pass a value rounded down to 0 to this API when a finite timeout is intended.

`Duration.toNanos()` can throw `ArithmeticException` if the duration is too large; apply reasonable bounds or handle errors at the configuration boundary. Reject negative or zero budgets if the API contract requires a valid deadline.

## 4. Implementing an immutable Deadline and testing with a fake clock

The example below compiles on Java 17+. `Deadline` holds **a single** start timestamp and the total budget. `LongSupplier` allows using `System::nanoTime` in production or a fake clock during testing. The `main` program uses a fake clock, so the output is completely deterministic and independent of machine speed.

**File TimeoutBudgetDemo.java**

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public final class TimeoutBudgetDemo {

    static final class Deadline {
        private final LongSupplier nanoClock;
        private final long startedNanos;
        private final long budgetNanos;

        Deadline(Duration budget, LongSupplier nanoClock) {
            Objects.requireNonNull(budget, "budget");
            if (budget.isZero() || budget.isNegative()) {
                throw new IllegalArgumentException("budget must be positive");
            }
            this.budgetNanos = budget.toNanos();
            this.nanoClock = Objects.requireNonNull(nanoClock, "nanoClock");
            this.startedNanos = nanoClock.getAsLong();
        }

        long remainingNanos() {
            long elapsed = nanoClock.getAsLong() - startedNanos;
            if (elapsed < 0 || elapsed >= budgetNanos) {
                return 0L;
            }
            return budgetNanos - elapsed;
        }

        long requireRemainingNanos() throws TimeoutException {
            long remaining = remainingNanos();
            if (remaining == 0L) {
                throw new TimeoutException("Overall timeout budget exhausted");
            }
            return remaining;
        }
    }

    // Method applicable to a real executor; main only verifies the calculation with a fake clock.
    static <T> T executeWithinBudget(
            ExecutorService executor,
            Callable<T> work,
            Deadline deadline)
            throws InterruptedException, ExecutionException, TimeoutException {

        // Do not enqueue more work when the budget is already exhausted.
        deadline.requireRemainingNanos();
        Future<T> future = executor.submit(work);

        try {
            // Re-measure after submit: time spent queuing the task also consumes the budget.
            T result = future.get(
                    deadline.requireRemainingNanos(), TimeUnit.NANOSECONDS);

            // If a strict deadline is required, do not accept a result that arrives past the deadline.
            if (deadline.remainingNanos() == 0L) {
                throw new TimeoutException("Result arrived after deadline");
            }
            return result;
        } catch (TimeoutException e) {
            future.cancel(true);
            throw e;
        } catch (InterruptedException e) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw e;
        }
    }

    private static void printRemaining(String label, Deadline deadline) {
        long milliseconds =
                TimeUnit.NANOSECONDS.toMillis(deadline.remainingNanos());
        System.out.println(label + ": " + milliseconds + " ms");
    }

    public static void main(String[] args) throws Exception {
        AtomicLong fakeNanos = new AtomicLong(0L);
        Deadline deadline =
                new Deadline(Duration.ofMillis(250), fakeNanos::get);

        printRemaining("Ban dau", deadline);
        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(80));
        printRemaining("Sau A", deadline);
        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(120));
        printRemaining("Sau B", deadline);
        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(60));
        printRemaining("Sau C", deadline);

        try {
            deadline.requireRemainingNanos();
        } catch (TimeoutException e) {
            System.out.println("Tu choi buoc tiep theo: het budget");
        }
    }
}
~~~

Compile and run:

~~~bash
javac TimeoutBudgetDemo.java
java TimeoutBudgetDemo
~~~

Exact stdout:

~~~text
Ban dau: 250 ms
Sau A: 170 ms
Sau B: 50 ms
Sau C: 0 ms
Tu choi buoc tiep theo: het budget
~~~

Note: `executeWithinBudget` is a method **usable with a real executor** but is not called by `main`; the stdout above only illustrates the deadline calculation. In a real environment, initialize `Deadline` with `System::nanoTime`, create an executor with a managed lifecycle, and pass **the same Deadline instance** through all steps. Do not use a fake clock to drive the real timeout of `Future.get`: `Future` uses real time.

Conceptual example of chaining two steps on the same executor and deadline, placed **inside** a method that already has `pool` and `deadline` variables:

~~~java
String first = executeWithinBudget(pool, () -> "step-A", deadline);
String second = executeWithinBudget(pool, () -> first + "/step-B", deadline);
~~~

This is a snippet to be embedded into a program, not a standalone Java file. In a real application, each `Callable` contains work that may block; `Future.get` computes the remaining time right before waiting.

## 5. Future, ExecutorService, and cancelling work after timeout

`Future.get(timeout, TimeUnit.NANOSECONDS)` only limits **how long the calling thread waits for the result**. When `TimeoutException` is thrown, the task does not stop automatically. Therefore, the example method calls `future.cancel(true)` upon expiration.

Implications and limitations:

1. If the task is still in the queue and has not started, cancellation may prevent it from running.
2. If the task is already running, `cancel(true)` attempts to **interrupt** the executing thread; whether it stops depends on whether the task and underlying libraries cooperate with interruption.
3. A task performing I/O or native calls that do not support interruption may continue running even though the `Future` is in the cancelled state. Timeouts must be configured at the corresponding I/O layer, and resources must be closed when needed.
4. If the thread calling `Future.get` receives `InterruptedException`, cancel the pending work, restore the interrupted flag at the appropriate boundary, and propagate the error/cancellation upward. Do not swallow the interrupt and start retrying as if nothing happened.
5. If the `Callable` throws an exception, `Future.get` throws `ExecutionException` wrapping the cause. **ExecutionException does not mean timeout**; the root cause must be preserved and classified.

An `ExecutorService` may have a full queue or reject tasks (`RejectedExecutionException`). Waiting in the queue also consumes the budget; `Future.get`'s timeout is measured **from the moment `get` is called**, whereas the overall budget is measured from the start of the task. If the task finishes after the program has already exceeded its deadline, a strict policy may reject the result, as the example does.

Do not create a new executor for each step to "reset" the time, and do not call `shutdownNow` on an application-wide shared executor just because a single request timed out. The executor's owner manages its lifecycle; the current request only cancels the `Future` belonging to it.

## 6. Applying to locks, queues, and other waiting points

Every waiting point must fetch **remaining right before the call**. Do not hold onto a stale remaining value and reuse it across multiple operations.

### Bounded lock waiting

~~~java
long waitNanos = deadline.requireRemainingNanos();
if (!lock.tryLock(waitNanos, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("Could not acquire lock before deadline");
}
try {
    // Protected region; check the deadline before the next waiting step.
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

This snippet requires `lock`, `deadline`, and `updateSharedState` from the enclosing program. `Lock.tryLock` with a timeout can throw `InterruptedException`; let it propagate or handle it according to your cancellation policy. Once the lock is **acquired**, `tryLock`'s timeout does not force the body of the critical section to stop: keep critical sections short, avoid long blocking I/O inside a lock, and check the deadline at appropriate boundaries.

### Waiting for an item from a BlockingQueue

~~~java
long waitNanos = deadline.requireRemainingNanos();
Message message = queue.poll(waitNanos, TimeUnit.NANOSECONDS);
if (message == null) {
    throw new TimeoutException("No message before deadline");
}
~~~

`Message` and `queue` are application types/variables, so this is an integration illustration. Distinguish a `null` caused by `queue.poll` timing out from a business value: `BlockingQueue` does not permit `null` elements.

### Waiting on a thread or condition

`Condition.awaitNanos(remaining)` takes nanoseconds and returns the remaining time per the API's contract; the condition must be checked in a **while loop** because spurious wakeups can occur. Meanwhile, `Thread.join(long millis)` has the special case `join(0)` = wait indefinitely. If you must use `join` with a budget under 1 ms, handle the remainder properly or choose an API with appropriate precision; do not round down to 0 and end up waiting forever.

**Non-waiting time** (CPU, serialization, condition checks, queuing, logging) still consumes the budget. Blocking API timeouts do not cover these segments. For CPU-intensive tasks, cooperative checkpoints checking `Thread.interrupted()` or the deadline are needed, rather than only setting a timeout on `Future.get`.

## 7. Sequential steps, retries, and backoff

For a sequential pipeline A → B → C, all three share a single deadline:

1. Create the deadline once **before A**.
2. Before A, compute `remaining`; pass it to A's waiting operation.
3. When A finishes, recompute `remaining` from the clock; use it for B.
4. Repeat for C. If `remaining == 0`, refuse to start the next step and propagate a timeout result upward.

When retrying, **all attempts share the same deadline**. For example, with a 500 ms budget, if the first attempt takes 280 ms and backoff takes 100 ms, the second attempt only has about 120 ms left. Do not repeat `timeout = 500 ms` on every attempt. Respect the maximum attempt count and only retry genuinely recoverable errors; a task whose budget is exhausted should not continue retrying.

To cap the timeout per attempt:

~~~java
long remaining = deadline.requireRemainingNanos();
long attemptLimit = TimeUnit.MILLISECONDS.toNanos(150);
long thisAttemptTimeout = Math.min(remaining, attemptLimit);
~~~

After handling an error, check `remaining` before sleeping for backoff; if the backoff exceeds `remaining`, do not sleep past the deadline and then retry. `TimeUnit.NANOSECONDS.sleep(...)` or `Thread.sleep(Duration)` (Java 19+) is interruptible, and the wakeup time is only approximate; recheck the deadline after waking up. On Java 17, use `TimeUnit.NANOSECONDS.sleep(nanos)`.

**Important trade-off:** a budget does not solve idempotency on its own. If a step has already performed a side effect (sent a command, written data) and the caller times out, retrying can duplicate the side effect. Use operation identifiers, idempotency keys, deduplication, or result-verification strategies when business logic requires it.

## 8. Parallel steps and CompletableFuture

If A and B run in parallel from the same deadline, the total wall-clock time is close to **max(time of A, time of B)** plus coordination overhead, rather than the sum of the two times by default. However, both must still receive the remaining time from the **same shared budget**. When one branch times out, the system must decide whether to abort the entire task, use a partial result, or fall back; this is a business policy, not something a timeout API can infer automatically.

Example when you only want to bound the aggregate wait time:

~~~java
long remaining = deadline.requireRemainingNanos();
CompletableFuture<Void> combined =
        CompletableFuture.allOf(futureA, futureB);
combined.get(remaining, TimeUnit.NANOSECONDS);
~~~

The snippet above assumes `futureA` and `futureB` have already been created, `deadline` is in scope, and the futures are `CompletableFuture` instances. If `combined.get` times out, **the two underlying tasks may still be running**. Cancel or close resources in the branches according to their contracts; calling `cancel` on a `CompletableFuture` does not guarantee interrupting a task created by `supplyAsync`.

`CompletableFuture.orTimeout(timeout, unit)` completes **that CompletableFuture itself** with a `TimeoutException` if it is not done yet; `completeOnTimeout(value, timeout, unit)` completes it with a fallback value. Both are **future-completion** policies, not mechanisms that guarantee background threads are interrupted or I/O is cancelled. Supply the timeout from `remaining` rather than calling `orTimeout` with a fixed constant at each step.

When forking multiple branches, record the deadline **before forking**. If you only create the deadline after the branches have been running for a while, initial startup and queuing costs are left out of the budget.

## 9. Propagating budgets across APIs or other processes

`System.nanoTime` on JVM A and JVM B **do not share the same time origin**; never send an absolute `nanoTime` value from A to B and compare it on B. At an inter-process call boundary, you can transmit the **remaining duration** as a relative duration, account for transmission time and appropriate overhead, and then create a new local deadline based on the receiver's `System.nanoTime`. If a protocol uses calendar timestamps (such as an epoch deadline), you must account for clock skew, network delay, and clock reliability on both sides.

In multi-hop applications, the receiver must not re-grant the original budget at each hop. The allowed processing duration downstream must be bounded by the remaining time provided by upstream and the hop's own local limit.

With Java `HttpClient`, request timeout and connect timeout have their own scopes; do not assume they cover all preparation, queuing, parsing, and retry steps of a pipeline. Set the timeout from `remaining` at the time of the API call, and re-measure the budget after it returns. Understand the exception types and cancellation semantics of each I/O API you use.

## 10. Expiration policies: fail, fallback, or partial result?

Before implementing, define the task's contract clearly:

| Policy | When to apply | What to uphold |
| --- | --- | --- |
| Fail fast with `TimeoutException` | Steps depend on each other; complete results are required | Do not start new steps after expiration; cancel cancellable work |
| Return fallback | A valid fallback value exists | Fallback must be cheap, precomputed, or still within budget |
| Return partial result | Business logic allows missing branches | Mark the status as partial; do not silently treat it as complete |
| Best-effort cleanup | Resources must be closed | Cleanup is bounded and runs in `finally`; record if it exceeds the deadline |

Cleanup and resource closing also take time. A deadline for the **business processing path** cannot necessarily skip mandatory release steps such as `unlock`, `close`, or transaction rollback. Design a separate cleanup policy, keep release operations short, and avoid using an unbounded timeout when already past the deadline.

Do not turn every timeout into an `InterruptedException`: `TimeoutException` means **the deadline expired**, whereas `InterruptedException` means **the thread was requested to be interrupted**. The two signals must be distinguished in logs, metrics, and control flow.

## 11. Common mistakes and how to fix them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Each step uses the full timeout | Total latency grows with the number of steps | Pass the same `Deadline` through the pipeline |
| Compute `remaining` once and reuse it | Ignores CPU, queue, retry, and backoff | Recompute before every blocking call |
| Use `currentTimeMillis` to measure elapsed time | Wall-clock can be adjusted | Use `System.nanoTime` within a single JVM |
| Call `Future.get(timeout)` and assume the task stopped | `get` only stops waiting | Cancel the `Future`, interrupt cooperatively, and set I/O timeouts |
| Catch `InterruptedException` and retry | Ignores cancellation request | Propagate the error or restore the interrupt and stop properly |
| Convert nanoseconds to millis and call `join(0)` | `join(0)` means wait forever | Avoid rounding down to 0; use an appropriate API |
| Create a new deadline on every retry | Resets the budget | All retries share the original deadline |
| Set timeouts only on individual `CompletableFuture` branches | No overall limit | Set a task-wide deadline; handle cancellation per branch |
| Use `nanoTime` from another process | Incompatible time origins | Pass remaining duration or use a deadline protocol accounting for skew |
| Treat timeout as proof that no side effect occurred | The task may have written data before expiring | Design for idempotency and verify state |

## 12. Testing and observing behavior

Test deadline calculations using a **fake clock** so they do not depend on the scheduler: initial `remaining`, decrease after each step, exact expiration boundary, past-deadline behavior, and invalid budgets. The runnable program in section 4 is an example of such boundary testing.

Additionally, integration tests with real executors and synchronization are needed:

- **Queue delay**: tasks waiting in the executor queue must also consume the budget.
- **Mid-pipeline timeout**: A completes, but B starts when `remaining` is insufficient; B may only wait for the remaining time.
- **Interruption**: cooperative tasks stop and release resources; callers do not swallow `InterruptedException`.
- **Non-cooperative tasks**: `Future.cancel(true)` returns, yet the task may keep running; real limitations must be recognized.
- **Retry/backoff**: the budget does not reset after a failed attempt.
- **Parallelism**: when one branch expires, remaining branches are cancelled or allowed to complete according to policy.
- **Side effects**: retrying after a timeout does not duplicate non-idempotent operations.

In production, record total elapsed time, `remaining` at the start of each step, queue wait time, retry count, timeouts by source, and cleanup outcomes. Use a monotonic clock to measure durations; if timestamps are needed for logs, record wall-clock timestamps **separately**. Avoid logging sensitive data from tasks.

## 13. Design checklist before going to production

1. Define the task-wide budget and the true start point (before enqueue/I/O).
2. Create a single `Deadline` using a monotonic clock and pass the same instance through all intra-JVM steps.
3. Before **every** blocking operation, fetch `remaining`; stop at 0 and combine with step-specific limits via `min` when needed.
4. Ensure async branches have clear cancellation, interruption, I/O timeout, and cleanup policies.
5. Include retries, backoff, queue wait, and intermediate processing in the same budget.
6. Test calculations with a fake clock; run real tests for cancellation, contention, resource handling, and side effects.

**Key takeaway:** A timeout on each individual step does not add up to a timeout for the entire pipeline. Only a shared deadline, continuously recomputed remaining time, and cooperative cancellation enable a Java concurrency task to respect its overall time limit.
