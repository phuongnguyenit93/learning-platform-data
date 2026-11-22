# Future.State, resultNow() and exceptionNow() in Java 21+

## 1. The Problem: Reading Future State and Result Without Blocking

`Future<V>` represents the result of an asynchronous computation. Previously, when holding a `Future`, you would typically combine `isDone()`, `isCancelled()`, and `get()` to distinguish between a successful result, a failure, or a cancellation. However, `isDone()` only indicates that the task has completed in a broad sense; it **does not distinguish normal completion from failure or cancellation**. `get()` can **block** until the task completes and throws the corresponding exceptions.

New methods on `java.util.concurrent.Future`:

- `Future.State state()`: returns the **observable state** of the computation.
- `V resultNow()`: retrieves the result of a computation that completed **normally**, without waiting.
- `Throwable exceptionNow()`: retrieves the exception from a computation that completed **with a failure**, without waiting.

In Java 21, the `Future.State` enum has four states: **`RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`**.

> **Version note:** This lesson uses **JDK 21 or later** per the topic, but the three APIs `state()`, `resultNow()`, and `exceptionNow()` were actually introduced in **Java 19** (the Javadoc states “Since: 19”). Therefore, you should not claim they were “first added in Java 21”. They do not exist on the `Future` interface in Java 17. All directly compiled examples below use `javac` and `java` from **JDK 21+**, not Java 17.

### Objectives

After this lesson, you will be able to:

1. Understand the semantics of the four `Future.State` values, especially why `RUNNING` **does not necessarily mean actively running on a CPU**.
2. Call `resultNow()` only after `state() == SUCCESS` and `exceptionNow()` only after `state() == FAILED`.
3. Distinguish `IllegalStateException` caused by invalid state access from `ExecutionException`, `CancellationException`, and `InterruptedException` thrown by `get()`.
4. Know when you need to **wait** with `get()` and when you only need to **inspect immediately** with the three new APIs.
5. Apply them to `FutureTask`, `CompletableFuture`, `ExecutorService.submit` tasks, and `ScheduledFuture`.
6. Avoid confusing `CANCELLED` with a guarantee that the worker has stopped and finished cleanup.
7. Design around general Java principles of safe publication, concurrency cancellation, and observability, without relying on any framework.

## 2. Traditional Future and the Problem of Asking the Wrong Question

A familiar Java 17 pattern:

~~~java
// Java 17+ pattern, not a standalone program.
Future<Integer> future = executor.submit(() -> calculate());

if (future.isDone()) {
    try {
        Integer value = future.get();
        use(value);
    } catch (ExecutionException failed) {
        report(failed.getCause());
    } catch (CancellationException cancelled) {
        recordCancellation();
    }
}
~~~

Even if you check `isDone()` first, `get()` still forces the caller to handle multiple outcome paths. If `future` is not done yet, `get()` without a timeout can wait indefinitely; if the task is cancelled, `isDone()` still returns true; if the task throws an exception, `isDone()` also returns true.

With Java 21+, you can **query the outcome directly** and retrieve the corresponding result:

~~~java
// Java 21+ pattern, not a standalone program.
switch (future.state()) {
    case RUNNING -> notePending();
    case SUCCESS -> use(future.resultNow());
    case FAILED -> report(future.exceptionNow());
    case CANCELLED -> recordCancellation();
}
~~~

This pattern cleanly separates the four branches. However, it does not replace `get()` where you **must wait** for a result; `resultNow()` is not designed to wait for a running task to finish.

### Why is “non-blocking inspection” useful?

- Displaying a progress dashboard: how many Futures are unfinished, succeeded, failed, or cancelled.
- Collecting results from **already completed** tasks without blocking the aggregating thread.
- Aggregating errors from finished Futures and classifying causes for logging or reporting.
- Classifying a `ScheduledFuture` that is waiting for its trigger time or has been cancelled.
- Interacting with `CompletableFuture`/`FutureTask` through the `Future` contract without inferring state from a chain of try/catch blocks around `get()`.

You **should not** poll `state()` continuously in a busy loop just to wait for a result; when the goal is to wait, choose `get()`/`get(timeout, unit)`, a completion callback, or an appropriate coordination primitive.

## 3. Future.State: Four States to Remember

### 3.1. The Enum and Its Meaning

In Java 21:

~~~java
// Enum constant names, not a standalone program.
Future.State.RUNNING
Future.State.SUCCESS
Future.State.FAILED
Future.State.CANCELLED
~~~

| State | Contract meaning | Result and how to retrieve it |
| --- | --- | --- |
| `RUNNING` | The computation has **not completed** | Cannot yet call `resultNow()` or `exceptionNow()` to get an outcome |
| `SUCCESS` | The computation completed **normally** | `resultNow()` retrieves the value, even when a valid result is `null` |
| `FAILED` | The computation completed with an **exception** | `exceptionNow()` retrieves the original `Throwable` |
| `CANCELLED` | The computation was **cancelled according to the Future state** | There is no result/exception of a `FAILED` completion to retrieve via the two `Now` methods |

This enum has no `NEW`, `QUEUED`, `WAITING`, or `TERMINATED` values. Therefore, **`RUNNING` simply means “not completed”**. A task that **has not been picked up by a worker yet**, is sitting in a queue, is waiting for a scheduled delay, or is actively executing can all appear as `RUNNING`. Do not use it to conclude that a thread has started executing the task.

### 3.2. Outcome State Transitions

~~~text
                       +----------------+
                       |    RUNNING     |
                       | (not completed)|
                       +-------+--------+
                               |
             +-----------------+-----------------+
             |                 |                 |
         completed      threw exception   cancel accepted
             |                 |                 |
       +-----v-----+     +-----v-----+     +-----v-------+
       |  SUCCESS  |     |  FAILED   |     | CANCELLED   |
       +-----------+     +-----------+     +-------------+
~~~

For a normal `Future`, a terminal outcome state does not transition back to `RUNNING`. `CANCELLED` may be observed immediately after cancellation is accepted, **before all code inside the worker finishes cleanup**.

Do not assume that every implementation notifies or runs callbacks in a strict order matching how you call `state()`. This is a **state snapshot**, not a persistently queued event.

### 3.3. Sampling Time and Concurrency

~~~java
// Observation pattern, not a standalone program.
Future.State seen = future.state();

if (seen == Future.State.RUNNING) {
    // Immediately afterward, the worker may already have completed.
}
~~~

A `RUNNING` result can become stale the instant the method returns. Calling `state()` holds no lock guaranteeing that the `Future` remains incomplete in the next moment.

Conversely, if you observe `SUCCESS`/`FAILED`/`CANCELLED` on a `Future` that honors its contract, that is a terminal outcome; `resultNow()`/`exceptionNow()` apply on their respective branches. Recording these terminal states is useful for reporting outcomes, but the **lifecycle of external side effects** may still require a separate confirmation channel upon cancellation.

## 4. resultNow(): Reading a Successful Result Immediately

### 4.1. Contract

`V resultNow()` returns the computed result **without waiting** when the `Future` has completed normally.

~~~java
// Java 21+ pattern, not a standalone program.
if (future.state() == Future.State.SUCCESS) {
    V result = future.resultNow();
    consume(result);
}
~~~

When does `resultNow()` throw `IllegalStateException`?

- The `Future` has not completed (`RUNNING`).
- The `Future` completed with an exception (`FAILED`).
- The `Future` was cancelled (`CANCELLED`).

**Important:** `SUCCESS` does not mean the value is non-`null`. For example, a submitted `Callable<Void>` or `Runnable` can complete normally with a `null` result. `resultNow() == null` is not a failure signal.

### 4.2. Why Not Use resultNow() Like get()?

`get()` is meant to **wait** for the task to complete (if it has not finished yet) and communicate outcomes or errors via `ExecutionException`, `CancellationException`, and `InterruptedException`. `resultNow()` is meant to **read an already available result** and surface API misuse as `IllegalStateException` if the state is wrong.

If the caller genuinely needs the value to compute the next step, it can use:

~~~java
// Result-waiting pattern, usable since Java 5; not standalone.
try {
    Integer answer = future.get(2, TimeUnit.SECONDS);
    process(answer);
} catch (TimeoutException timedOut) {
    // Decide deadline/cancel policy per business logic.
}
~~~

This snippet also needs to handle or propagate `InterruptedException` and `ExecutionException` per the method contract. `TimeoutException` means the wait timed out; it **does not automatically cancel the Future**.

## 5. exceptionNow(): Reading the Cause When Future Has FAILED

`Throwable exceptionNow()` returns the throwable that caused the computation to fail when the state is `FAILED`:

~~~java
// Java 21+ pattern, not a standalone program.
if (future.state() == Future.State.FAILED) {
    Throwable failure = future.exceptionNow();
    report(failure);
}
~~~

In the Java 21 Javadoc, `exceptionNow()` throws `IllegalStateException` if the task:

- Has not completed (`RUNNING`).
- Completed normally (`SUCCESS`).
- Was cancelled (`CANCELLED`).

`FAILED` is the state of completing by exception, not “was cancelled”. Calling `cancel(true)` to send an interrupt to the worker, causing the worker to catch `InterruptedException`, does **not** force the `Future` to become `FAILED`; if the `Future` state was successfully cancelled, the outcome is typically `CANCELLED`.

### 5.1. Comparison with Future.get()

When the task has `FAILED`:

~~~java
// Java pattern, not standalone.
try {
    future.get(); // May wait if not finished yet.
} catch (ExecutionException wrapper) {
    Throwable cause = wrapper.getCause();
    report(cause);
}
~~~

`get()` throws `ExecutionException` wrapping the cause. `exceptionNow()` returns the underlying `Throwable` cause directly **when already FAILED**; the caller does not need to unwrap `ExecutionException` in that branch.

Do not try calling both `Now` methods “to see which one doesn't throw”. **Reading `state()` first and choosing the right method** is clearer and avoids using exceptions for normal control flow.

## 6. Example 1 — Observing All Four States (Java 21+)

We create four `CompletableFuture` instances with intentionally set states. No extra threads or `sleep` are needed, so the output is deterministic.

Create `FutureStatesDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;

public class FutureStatesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> pending =
            new CompletableFuture<>();

        CompletableFuture<Integer> success =
            CompletableFuture.completedFuture(42);

        CompletableFuture<Integer> failed =
            CompletableFuture.failedFuture(
                new IllegalArgumentException("bad input")
            );

        CompletableFuture<Integer> cancelled =
            new CompletableFuture<>();
        cancelled.cancel(false);

        System.out.println("pending = " + pending.state());
        System.out.println("success = " + success.state());
        System.out.println("failed = " + failed.state());
        System.out.println("cancelled = " + cancelled.state());

        System.out.println("result = " + success.resultNow());
        System.out.println("failure type = "
            + failed.exceptionNow().getClass().getSimpleName());
        System.out.println("success state constant = "
            + Future.State.SUCCESS);
    }
}
~~~

Compile/run with **JDK 21+**:

~~~bash
javac FutureStatesDemo.java
java FutureStatesDemo
~~~

Stdout:

~~~text
pending = RUNNING
success = SUCCESS
failed = FAILED
cancelled = CANCELLED
result = 42
failure type = IllegalArgumentException
success state constant = SUCCESS
~~~

**Exact analysis:**

1. `pending` has not had `complete(...)` called on it, so `state()` is `RUNNING`, even though **no thread is actually running it**.
2. `completedFuture(42)` already has a result from the start, so its state is `SUCCESS` and `resultNow() == 42`.
3. `failedFuture(...)` completed exceptionally, so its state is `FAILED` and `exceptionNow()` returns the original `Throwable`.
4. `cancel(false)` on an incomplete `CompletableFuture` sets its state to `CANCELLED`. There is no worker to interrupt in this example.
5. `Future.State` is an enum nested in the `Future` interface, not an enum specific to `CompletableFuture`.

This is a very clear way to learn because it does not mix outcome cases with scheduler nondeterminism.

## 7. Example 2 — Guarding the Now Methods and IllegalStateException (Java 21+)

Create `FutureNowGuardsDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class FutureNowGuardsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> pending =
            new CompletableFuture<>();
        CompletableFuture<String> ok =
            CompletableFuture.completedFuture(null);
        CompletableFuture<String> bad =
            CompletableFuture.failedFuture(
                new IllegalStateException("business failure")
            );

        try {
            pending.resultNow();
        } catch (IllegalStateException expected) {
            System.out.println("pending resultNow rejected");
        }

        try {
            ok.exceptionNow();
        } catch (IllegalStateException expected) {
            System.out.println("success exceptionNow rejected");
        }

        try {
            bad.resultNow();
        } catch (IllegalStateException expected) {
            System.out.println("failed resultNow rejected");
        }

        System.out.println("null result success = "
            + (ok.state() == java.util.concurrent.Future.State.SUCCESS
                && ok.resultNow() == null));

        System.out.println("failed exception = "
            + bad.exceptionNow().getMessage());
    }
}
~~~

Compile/run:

~~~bash
javac FutureNowGuardsDemo.java
java FutureNowGuardsDemo
~~~

Stdout:

~~~text
pending resultNow rejected
success exceptionNow rejected
failed resultNow rejected
null result success = true
failed exception = business failure
~~~

**Note:** Both the exception representing a business failure and the exception caused by **invalid API usage** can be instances of `IllegalStateException`. In the example, `bad.exceptionNow()` returns the `IllegalStateException("business failure")` object from the task, whereas calling `bad.resultNow()` itself throws an `IllegalStateException` because the state is not `SUCCESS`. Do not conflate these two errors when logging.

When building user-facing APIs, it is generally better to **branch explicitly on state** rather than using `resultNow()`/`exceptionNow()` exceptions to probe state.

## 8. Example 3 — An ExecutorService Task in RUNNING Then SUCCESS

To demonstrate `RUNNING` when a task has been submitted to an executor but has not yet completed, we control the wait point using `CountDownLatch`. Do not use `Thread.sleep` to guess whether the worker has started.

Create `ExecutorFutureStateDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorFutureStateDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> future = pool.submit(() -> {
                started.countDown();
                release.await();
                return 21;
            });

            started.await();
            System.out.println("before = " + future.state());

            release.countDown();
            System.out.println("get = " + future.get());
            System.out.println("after = " + future.state());
            System.out.println("resultNow = " + future.resultNow());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile/run with JDK 21+:

~~~bash
javac ExecutorFutureStateDemo.java
java ExecutorFutureStateDemo
~~~

Stdout when the task is not interrupted:

~~~text
before = RUNNING
get = 21
after = SUCCESS
resultNow = 21
~~~

**Why is this deterministic?**

- The worker counts down `started` before waiting on `release`; main waits for `started` before calling `future.state()`.
- Main has **not** counted down `release` when printing `before`; the callable cannot return `21` until the latch opens. Thus the state is `RUNNING`.
- Main releases the worker via `release.countDown()`, then `future.get()` waits until the computation completes.
- After `get()` succeeds, `state()` is `SUCCESS` and `resultNow()` immediately returns `21`.
- The `finally` block always opens the latch to avoid stranding the worker if the caller throws an exception before releasing, and manages the pool lifecycle.

**Limitation:** Observing `RUNNING` should not lead code to conclude “the worker is currently occupying a CPU”. In this example, the worker is **waiting on a latch**. There is no `QUEUED`/`BLOCKED`/`WAITING` constant in `Future.State`.

## 9. Example 4 — exceptionNow with a Future from an Executor (Java 21+)

Create `ExecutorFailureNowDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorFailureNowDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> future = pool.submit(() -> {
                throw new IllegalArgumentException("invalid number");
            });

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("get cause = "
                    + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("state = " + future.state());
            System.out.println("exceptionNow = "
                + future.exceptionNow().getMessage());

            try {
                future.resultNow();
            } catch (IllegalStateException expected) {
                System.out.println("resultNow rejected");
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ExecutorFailureNowDemo.java
java ExecutorFailureNowDemo
~~~

Stdout:

~~~text
get cause = IllegalArgumentException
state = FAILED
exceptionNow = invalid number
resultNow rejected
~~~

`submit(...)` returns a `Future` holding the task's outcome. When the task has `FAILED`, `future.get()` throws `ExecutionException`; the `IllegalArgumentException` cause is wrapped in `getCause()`. Afterward, `future.state()` returns `FAILED`, while `exceptionNow()` returns the cause directly for handling/logging.

**Do not equate `exceptionNow` with a call that makes the task fail.** The task already threw the exception in the executor; `exceptionNow()` only **observes** a stored outcome. Calling `exceptionNow()` does not retry, cancel, or restart the task.

## 10. CANCELLED: Cancelling a Future Does Not Stop All Side Effects Immediately

### 10.1. Cancellation Can Arrive Before or During Execution

`Future.cancel(boolean mayInterruptIfRunning)` requests cancellation. If the task has not started yet, an accepted cancellation can prevent it from running. If the task has already started, `mayInterruptIfRunning == true` allows the implementation to attempt interrupting the thread running the task when that thread is known.

However, interruption is still a **cooperative mechanism**: the worker might be in a computation section that does not check the flag, holding resources, or running cleanup. Therefore:

- `future.state() == CANCELLED` does not guarantee that the worker has exited.
- `future.isDone() == true` can indicate a cancelled state rather than business completion.
- `future.get()` on a cancelled `Future` throws `CancellationException` and does not return a business result.
- `resultNow()` and `exceptionNow()` do not return a success/failure outcome on a `CANCELLED` Future; both methods throw `IllegalStateException` per contract.
- If you need to know that the worker has closed files, released resources, or recorded a final state, use a **separate** latch or confirmation channel.

### 10.2. Example 5 — CANCELLED and Signaling the Worker (Java 21+)

Create `FutureCancellationStateDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancellationStateDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        FutureTask<Integer> task = new FutureTask<>(() -> {
            entered.countDown();
            try {
                for (;;) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                return 0;
            } finally {
                finished.countDown();
            }
        });

        Thread worker = new Thread(task, "cancellable-worker");
        worker.start();
        entered.await();

        boolean accepted = task.cancel(true);
        finished.await();
        worker.join();

        System.out.println("cancel accepted = " + accepted);
        System.out.println("state = " + task.state());
        System.out.println("worker observed interrupt = "
            + interrupted.get());
        System.out.println("worker finished = " + !worker.isAlive());

        try {
            task.get();
        } catch (CancellationException ex) {
            System.out.println("get throws CancellationException");
        }
    }
}
~~~

Compile/run:

~~~bash
javac FutureCancellationStateDemo.java
java FutureCancellationStateDemo
~~~

Stdout when the worker encounters no unexpected interrupts or errors:

~~~text
cancel accepted = true
state = CANCELLED
worker observed interrupt = true
worker finished = true
get throws CancellationException
~~~

**Why is it still CANCELLED if the task returns `0` in catch?** `cancel(true)` accepted the cancellation of the `Future` before the worker finished. Returning a value afterward **does not change** the outcome state of an already cancelled `Future` to `SUCCESS`. `get()` on this `Future` throws `CancellationException`.

`entered` ensures the worker has entered the callable before main cancels it. If cancellation arrives right before the worker calls `sleep`, the interrupt flag still causes `sleep` to respond with an exception; if it arrives during `sleep`, the wait is interrupted. `finished` and `worker.join()` confirm that the final code path and thread have genuinely finished **before** the program prints the results.

This example has a `finished` channel because `CANCELLED` does not by itself indicate that resources have been cleaned up. In real applications, put cleanup in `finally` or try-with-resources, handle cleanup errors, and use explicit confirmation when business logic requires it.

## 11. ScheduledFuture Is Also a Future

`ScheduledExecutorService` can return a `ScheduledFuture<V>`. This interface both carries delay information (`Delayed`) and extends `Future<V>`, so you can use `state()`, `resultNow()`, and `exceptionNow()` in Java 21+.

### 11.1. One-Shot Scheduled Task

~~~java
// Java 21+ pattern, not a standalone program.
ScheduledFuture<String> future =
    scheduler.schedule(() -> "done", 2, TimeUnit.SECONDS);

if (future.state() == Future.State.RUNNING) {
    // May be waiting for its scheduled time or executing; not finished yet.
}
~~~

**`RUNNING` does not mean a scheduled task has reached its execution time.** A scheduled task waiting for its delay has not completed yet, so it is `RUNNING`. To query the remaining delay, use `getDelay(TimeUnit.MILLISECONDS)`, though this value is also just an instantaneous observation.

### 11.2. Example 6 — A Successful Scheduled Task and a Cancelled Scheduled Task (Java 21+)

Create `ScheduledFutureStateDemo.java`:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledFutureStateDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<String> immediate =
                scheduler.schedule(
                    () -> "ready", 0, TimeUnit.MILLISECONDS
                );

            ScheduledFuture<String> later =
                scheduler.schedule(
                    () -> "too late", 1, TimeUnit.DAYS
                );

            System.out.println("scheduled result = " + immediate.get());
            System.out.println("scheduled state = " + immediate.state());
            System.out.println("resultNow = " + immediate.resultNow());

            System.out.println("later before = " + later.state());
            later.cancel(false);
            System.out.println("later after = " + later.state());
            System.out.println("cancelled = "
                + (later.state() == Future.State.CANCELLED));
        } finally {
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                System.out.println("scheduler still shutting down");
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ScheduledFutureStateDemo.java
java ScheduledFutureStateDemo
~~~

Typical stdout with a stable system clock and the scheduler stopping within 5 seconds:

~~~text
scheduled result = ready
scheduled state = SUCCESS
resultNow = ready
later before = RUNNING
later after = CANCELLED
cancelled = true
~~~

The first scheduled task has a 0 delay and its callable returns `"ready"`; `get()` waits for completion, and then `resultNow()` reads the available result. The `later` task has a one-day delay, so it has not completed when checked immediately in a normal run: `RUNNING` simply means “not completed”. `cancel(false)` cancels the unstarted task, changing the `Future` state to `CANCELLED`. No `"too late"` result is published.

**Note on determinism:** The line `later before = RUNNING` relies on normal execution timing, a 1-day delay, and the absence of external operations altering the clock or extreme scheduling delays; it is not a general proof that a delay always lasts exact wall-clock time. If you need a completely deterministic state test, use an incomplete `CompletableFuture` as in Example 1 or a latch blocking the callable as in Example 3.

### 11.3. Periodic ScheduledFuture

`scheduleAtFixedRate(...)` and `scheduleWithFixedDelay(...)` return a `ScheduledFuture<?>` for a repeating execution sequence:

- While the repeating task remains scheduled, the `Future` typically stays in `RUNNING`: individual runs completing does **not** mean the whole sequence is `SUCCESS`.
- For a normal indefinitely repeating task, calling `get()` can wait forever unless it is cancelled, fails, or has another termination policy.
- If a run throws an unhandled exception, subsequent executions are **suppressed** per the scheduled executor contract, and the `Future` can complete as `FAILED`.
- When cancellation is accepted, the `Future` transitions to `CANCELLED`; a currently running task may still need to cooperate to stop/clean up.

Do not expect `Future.State.SUCCESS` after each periodic tick. If you need per-run success/failure statistics, the task should record metrics/results on each tick via its own mechanism.

## 12. Are state(), resultNow(), and exceptionNow() Truly Non-Blocking?

By API contract, these are operations that **observe the outcome without waiting for the task to complete**. On the `Future` interface, they are provided as default methods:

- The default `resultNow()` checks `isDone()` and then calls `get()` when the `Future` is already done.
- The default `exceptionNow()` checks `isDone()`/`isCancelled()` and uses `get()` to retrieve the exception if already finished.
- The default `state()` uses `isDone()`, `isCancelled()`, and `get()` to classify the outcome.

Therefore, **a contract-compliant implementation must ensure consistency between completion state and `get()`**. `FutureTask` and `CompletableFuture` may have dedicated implementations or optimized paths depending on the JDK. Do not build a custom `Future` where `isDone() == true` while `get()` still blocks for a long time or forever; that is an inconsistent contract and can cause the observation methods to behave unexpectedly.

For an already terminal `Future`, reading the outcome does not wait for the task to keep running. However, **the CPU execution duration of a method call** is not a hard real-time deadline guarantee: timing still depends on the scheduler, internal locks, JIT compilation, and value handling.

### 12.1. Compatibility Implications of Default Methods

Because the three methods were added as **default methods on `Future`**, legacy classes implementing `Future` can still inherit the default behavior when running on a newer JDK, provided they obey the contracts of `isDone`, `isCancelled`, and `get`. However, source code calling `resultNow()` must still be **compiled against Java 19+ APIs**, such as JDK 21's `javac`; with `--release 17`, those three methods do not exist in the target API.

Do not use reflection to “invent” method calls when the application targets Java 17. If Java 17 support is required, keep `isDone/isCancelled/get`, a compatibility wrapper, or a separate API design.

## 13. Comparing get(), get(timeout), join(), and the Now Methods

| API | Can wait for result? | Success | Failure | Cancellation |
| --- | --- | --- | --- | --- |
| `Future.get()` | **Yes** | Returns `V` | `ExecutionException` | `CancellationException` |
| `Future.get(timeout, unit)` | **Bounded** | Returns `V` | `ExecutionException` or timeout | `CancellationException` |
| `Future.state()` | **Does not wait for task completion** | `SUCCESS` | `FAILED` | `CANCELLED` |
| `Future.resultNow()` | **No** | Returns `V` | `IllegalStateException` | `IllegalStateException` |
| `Future.exceptionNow()` | **No** | `IllegalStateException` | Returns `Throwable` | `IllegalStateException` |
| `CompletableFuture.join()` | **Yes** if not done | Returns `V` | `CompletionException` (typically) | `CancellationException` |
| `CompletableFuture.getNow(default)` | **No** | Returns value (if done) | `CompletionException` (typically) | `CancellationException` |

**Details to remember:**

- `Future.get()` can also throw `InterruptedException` when the **waiting thread** is interrupted.
- `Future.get(timeout, unit)` adds `TimeoutException`; a timeout **does not automatically cancel**.
- `CompletableFuture.getNow(default)` uses the fallback value when **not yet completed**, whereas `Future.resultNow()` **throws `IllegalStateException`** when not yet completed.
- `Future.resultNow()` belongs to the `Future` interface, so it also applies to Futures returned by executors/schedulers, not just `CompletableFuture`.
- `CompletableFuture.join()` belongs to the `CompletableFuture` class, not every `Future`.

### 13.1. Why Not Use isDone() && !isCancelled() to Infer SUCCESS?

~~~java
// WRONG: insufficient to distinguish SUCCESS from FAILED.
if (future.isDone() && !future.isCancelled()) {
    Integer value = future.resultNow(); // May throw IllegalStateException.
}
~~~

This condition is also true when the `Future` has `FAILED`. If you want to call `resultNow()`, use `future.state() == Future.State.SUCCESS`; if `FAILED`, call `exceptionNow()`.

### 13.2. What If the Result Is null?

`null` can be the result of a successful task, such as `submit(Runnable)` without a specific result or a `Callable<String>` returning `null`. Use `state()` instead of comparing `resultNow() == null` to decide whether a task failed or succeeded.

## 14. Aggregating a List of Futures Without Blocking

An application may hold a collection of Futures corresponding to multiple tasks. If you need to **collect currently available results without blocking**, you can filter by state first.

### Aggregation Pattern

~~~java
// Java 21+, illustrative snippet inside a method with List<Future<Integer>>.
List<Integer> successes = futures.stream()
    .filter(f -> f.state() == Future.State.SUCCESS)
    .map(Future::resultNow)
    .toList();

List<Throwable> failures = futures.stream()
    .filter(f -> f.state() == Future.State.FAILED)
    .map(Future::exceptionNow)
    .toList();
~~~

Here `List` and `Future` must be imported. This pattern does not block waiting for unfinished tasks; `RUNNING`/`CANCELLED` Futures are skipped. If a `Future` transitions from `RUNNING` to `SUCCESS` right after being checked, its result may **not appear in the current scan**; a later scan can pick it up.

If the requirement is “wait for **all** and aggregate once”, do not scan repeatedly like this. You can use `Future.get()` on each task with a deadline, or `CompletableFuture.allOf(...)` with appropriate exception semantics.

### 14.1. Example 7 — Deterministic Aggregation (Java 21+)

Create `FutureCollectNowDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;

public class FutureCollectNowDemo {
    public static void main(String[] args) {
        List<Future<Integer>> tasks = List.of(
            CompletableFuture.completedFuture(3),
            CompletableFuture.failedFuture(
                new IllegalArgumentException("broken")
            ),
            CompletableFuture.completedFuture(5),
            new CompletableFuture<>()
        );

        List<Integer> values = tasks.stream()
            .filter(f -> f.state() == Future.State.SUCCESS)
            .map(Future::resultNow)
            .toList();

        List<String> errors = tasks.stream()
            .filter(f -> f.state() == Future.State.FAILED)
            .map(f -> f.exceptionNow().getClass().getSimpleName())
            .toList();

        long unfinished = tasks.stream()
            .filter(f -> f.state() == Future.State.RUNNING)
            .count();

        System.out.println("values = " + values);
        System.out.println("errors = " + errors);
        System.out.println("unfinished = " + unfinished);
    }
}
~~~

Compile/run:

~~~bash
javac FutureCollectNowDemo.java
java FutureCollectNowDemo
~~~

Stdout:

~~~text
values = [3, 5]
errors = [IllegalArgumentException]
unfinished = 1
~~~

The four Futures have pre-built states, with no external workers running and no other threads updating them, so the filtered results and list order are fixed. `Stream.toList()` preserves the encounter order of the source `List`, and `Future::resultNow` is only called on Futures in `SUCCESS`.

In real applications, a collection of Futures can complete concurrently; an instantaneous summary is not an atomic snapshot of the **entire** task set. To guarantee every task is counted exactly once, you need a dedicated stateful outcome-collection protocol.

## 15. Java Memory Model and Result Consistency

The `Future` Javadoc describes the memory-consistency effect: **actions taken by the asynchronous computation happen-before actions following the corresponding `Future.get()` in another thread**. Therefore, `get()` is an important synchronization point when the caller receives a completed result.

JDK `Future` implementations also have mechanisms for safe completion and outcome publication. However, you should not treat `state()` as a protective lock for **arbitrary mutable data outside the Future**. A `SUCCESS` Future does not make other application objects immutable, and does not replace synchronization if the result holds a reference to an object that continues to be modified by another thread.

### 15.1. Distinguish Three Layers

1. **Task outcome:** whether the `Future` is `RUNNING`/`SUCCESS`/`FAILED`/`CANCELLED`.
2. **Task business data:** is the result data mutable, and is any thread still updating it?
3. **External side effects:** have file/network/database operations actually completed, rolled back, or cleaned up?

`Future.State` primarily addresses the first layer. `resultNow()` lets you retrieve the successful result of the first layer; if the value is a shared mutable object, the second layer still requires invariants and ownership. `CANCELLED` also does not guarantee that the third layer has stopped.

### 15.2. Do Not Fake Waiting with Thread.sleep

~~~java
// WRONG for coordination, not a standalone program.
Thread.sleep(50);
if (future.state() == Future.State.SUCCESS) {
    use(future.resultNow());
}
~~~

A 50ms sleep does not guarantee the task has completed. If the caller needs to wait, `get(timeout, unit)` expresses an explicit deadline; if the caller only wants to inspect the current state immediately, do not add `sleep`. Use a latch/barrier in tests when you need deterministic interleaving.

## 16. Common Pitfalls

| Pitfall | Why it is wrong | Correct approach |
| --- | --- | --- |
| Assuming the three APIs started in Java 21 | Javadoc states `Since: 19` | State **Java 19+**, with examples run on JDK 21+ |
| Assuming `RUNNING` = thread is actively executing | `RUNNING` means not completed, including queued/delayed | Use executor metrics/thread dumps to see active execution |
| Seeing `isDone() == true` and immediately calling `resultNow()` | `FAILED` and `CANCELLED` are also done | Check `state() == SUCCESS` |
| Calling `exceptionNow()` when `CANCELLED` | `CANCELLED` is not a `FAILED` outcome | Handle cancellation separately |
| Calling `resultNow()` on a `RUNNING` task for a “quick wait” | Throws `IllegalStateException`, does not wait | Use `get(timeout, unit)` if waiting is needed |
| Using `exceptionNow()` as a way to throw the original exception | The method **returns `Throwable`**, it does not throw it as the result | Decide to report/rethrow per contract |
| Treating `resultNow() == null` as an error | A successful task can return `null` | Classify via `state()` |
| Treating `cancel(true)` as meaning worker cleanup is finished | Future cancellation and worker lifecycle differ | Use a separate latch/ack/result channel |
| Treating each periodic task run as Future `SUCCESS` | The periodic schedule has not ended | Record outcomes per tick if needed |
| Polling `state()` in a spin loop | Wastes CPU and lacks a deadline contract | Blocking `get`, callbacks, or waiting primitives |
| Not closing scheduled/executor pools | Workers stay alive, tasks remain queued | `shutdown`, `awaitTermination`, fallback `shutdownNow` |
| Believing `get(timeout)` auto-cancels the task on timeout | Timeout only bounds the caller's wait | Decide `cancel` separately |
| Ignoring `InterruptedException` from `get()` | Loses the waiting thread's interruption signal | Propagate or restore the flag per contract |
| Ignoring the cause of `ExecutionException` | Loses information about the `FAILED` task | Read `getCause()` or `exceptionNow()` after `FAILED` |
| Treating `state()` as an atomic snapshot of an entire Future set | Each Future changes independently | Design an aggregation barrier if needed |
| Using `--release 17` with the new APIs | Java 17 `Future` lacks the three default methods | Compile with a Java 19+ target |

## 17. Review Checklist When Applying

- Are you compiling/running with **JDK 21+** or Java 19+ for the three new methods?
- Is `RUNNING` clearly distinguished from “actively running” on a worker?
- Is `resultNow()` only called when the `Future` is actually `SUCCESS`?
- Is `exceptionNow()` only called when the `Future` is actually `FAILED`?
- Is `CANCELLED` handled as a separate outcome rather than treated as `exceptionNow()`?
- When waiting for a result is required, does the code use `get()` or a bounded `get(timeout, unit)` instead of unbounded polling?
- For a `FAILED` Future, is the underlying `Throwable` cause reported instead of just printing `FAILED`?
- For nullable results, is a `null` `SUCCESS` distinguished from failure?
- For `ScheduledFuture`, is it understood that a delayed task can be `RUNNING` and a periodic task is not `SUCCESS` on each tick?
- Is Future cancellation state distinguished from worker shutdown/cleanup?
- Are executor/scheduler `shutdown` and timeouts managed to avoid leaking threads?
- If implementing a custom `Future`, are `isDone/isCancelled/get` consistent so the default methods work properly?
- Do you avoid assuming a single pass of `state()` calls over multiple Futures is a single atomic snapshot?
- When visibility of result data is needed, do you rely on `Future.get()` or an appropriate synchronization protocol?
- Is the module's Special Note followed by discussing only Java concurrency and standard JDK APIs?

## 18. Self-Check Questions

**1.** Does `Future.State.RUNNING` definitely mean a worker has started executing the task?

**No.** `RUNNING` only means the computation has not completed. A queued task or one waiting on a delay can also be `RUNNING`.

**2.** If `isDone()` returns true, is it safe to call `resultNow()`?

**You cannot infer that.** The `Future` may be `SUCCESS`, `FAILED`, or `CANCELLED`. Only call `resultNow()` when `state() == SUCCESS`.

**3.** What does `exceptionNow()` return when a task has `FAILED`?

It returns the stored **failure-causing `Throwable`**, without waiting. This differs from `get()`, which throws `ExecutionException` wrapping the cause.

**4.** Does `exceptionNow()` return `CancellationException` if the `Future` is `CANCELLED`?

Not according to this method's contract. For `CANCELLED`, `exceptionNow()` throws `IllegalStateException` because the `Future` is not `FAILED`. Calling `get()` on a cancelled `Future` is what throws `CancellationException`.

**5.** Can a `SUCCESS` Future return `null` from `resultNow()`?

Yes. `SUCCESS` describes the outcome, and does not require the result to be non-null.

**6.** Does `resultNow()` wait for the task to complete like `get()` does?

No. If the task has not completed or ended in a non-success state, it throws `IllegalStateException`.

**7.** Can a `ScheduledFuture` scheduled to run one day later report `RUNNING` right after scheduling?

Yes. In the `Future` enum, `RUNNING` only means “not completed”, not actively executing on a CPU.

**8.** A periodic task finishes its first execution. Must `ScheduledFuture.state()` be `SUCCESS`?

No. A periodic future normally still represents **subsequent executions**; while it remains scheduled, the overall task has not completed.

**9.** Does `Future.cancel(true)` changing the state to `CANCELLED` prove the worker has closed all resources?

No. Separate confirmation of cleanup completion is needed if the business logic requires it.

**10.** Were the three APIs first added in Java 21 or Java 19?

**Java 19.** They are available in Java 21; the examples use JDK 21+ to match the lesson environment.

**11.** Can `Future::resultNow` be used in a stream without checking the state?

It is unsafe when the stream contains `RUNNING`, `FAILED`, or `CANCELLED` Futures. Filter `f.state() == Future.State.SUCCESS` first.

**12.** If a Future has `FAILED`, how do `get()` and `exceptionNow()` differ in how they represent the exception?

`get()` throws `ExecutionException`, and you obtain the cause via `getCause()`. `exceptionNow()` returns the original `Throwable` directly when the `Future` has `FAILED`.

## 19. Summary and Official Documentation

**Quick reference:**

~~~text
Future.State.RUNNING   -> No outcome yet, do not call Now methods
Future.State.SUCCESS   -> future.resultNow()
Future.State.FAILED    -> future.exceptionNow()
Future.State.CANCELLED -> Handle cancellation separately; do not call result/exceptionNow
~~~

`Future.state()` helps classify an outcome without waiting. `resultNow()` and `exceptionNow()` let you read the exact completed outcome without calling `get()` to probe it. When you must **wait**, use `get()` and manage deadlines/cancellation; when you must **confirm cleanup**, use a separate completion channel. Always distinguish the `Future` outcome from the worker's state and from side effects in external systems.

Official documentation for verifying the contract and “Since: 19”:

- [Future (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Future.State (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.State.html)
- [ScheduledExecutorService (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)

**Remember:** Reading state **is not** waiting for completion; `SUCCESS`/`FAILED`/`CANCELLED` are three distinct outcomes, while `RUNNING` simply means “not done”. Choose the right API for the question your application actually needs to answer.
