# TimeUnit: Unit Conversion, Precision, and Multi-Step Time Budgets

## 1. What Problem Does TimeUnit Solve in Java Concurrency?

Concurrency APIs often need to express **wait times**, **timeouts**, **scheduling delays**, and **deadlines**. Bare numbers like `1000` are ambiguous: is that milliseconds, microseconds, or nanoseconds?

Java provides the `java.util.concurrent.TimeUnit` enum to pass a `long` value **together with its time unit**. For example:

```java
future.get(2, TimeUnit.SECONDS);
latch.await(500, TimeUnit.MILLISECONDS);
lock.tryLock(250, TimeUnit.MICROSECONDS);
executor.awaitTermination(5, TimeUnit.SECONDS);
scheduler.schedule(task, 100, TimeUnit.MILLISECONDS);
```

The snippets above are **API illustrations**; `future`, `latch`, `lock`, `executor`, `scheduler`, and `task` are declared appropriately in the application. Reading `2, SECONDS` is clearer than an unnamed `2000`.

However, using `TimeUnit` alone is not enough to write correct timeout code. Three categories of issues must be distinguished:

1. **Unit conversion:** `TimeUnit.convert`, `toNanos`, and `toMillis` can **truncate to 0 when converting to a coarser unit**, or **saturate** if the result exceeds `long`.
2. **Actual precision:** specifying a timeout in nanoseconds **does not guarantee the thread will be woken up at that exact nanosecond**; the JVM, operating system, scheduler, and CPU load affect the actual execution time.
3. **Multi-step time budgets:** if a workflow has a maximum total of 1 second, each step must not reuse **the full 1 second**. You need to measure **elapsed** time using a suitable clock, then pass the **remaining time** to the next step.

This is fundamental knowledge of **Future & Scheduling** in **general Java concurrency**, independent of any framework.

## 2. Units Supported by TimeUnit

`TimeUnit` is an `enum` with the following constants:

| Constant | Common Abbreviation | Relationship |
| --- | --- | --- |
| `NANOSECONDS` | ns | 1 nanosecond |
| `MICROSECONDS` | µs | 1 µs = 1,000 ns |
| `MILLISECONDS` | ms | 1 ms = 1,000 µs |
| `SECONDS` | s | 1 s = 1,000 ms |
| `MINUTES` | min | 1 minute = 60 s |
| `HOURS` | h | 1 hour = 60 minutes |
| `DAYS` | d | 1 day = 24 hours |

The `DAYS`, `HOURS`, and `MINUTES` units in `TimeUnit` are **fixed-length durations**, without accounting for calendars, time zones, or daylight saving time. For example, `DAYS.toHours(1)` is always `24`, not "the actual number of hours in a local day that might have a clock change."

To represent **calendar points in time**, use `Instant`, `ZonedDateTime`, or an appropriate `java.time` type. To represent **wait/timeout durations** in concurrency, `TimeUnit` combined with an elapsed-time clock is the standard choice.

## 3. Unit Conversion with `convert` and `toX`

There are two equivalent ways to express the same conversion:

```java
long millis = TimeUnit.MILLISECONDS.convert(3, TimeUnit.SECONDS);
long same = TimeUnit.SECONDS.toMillis(3);
```

Both yield `3000`.

**Parameter order of `convert`:**

```java
targetUnit.convert(value, sourceUnit);
```

This means the **unit receiving the call** is the target unit. For example:

```java
long seconds = TimeUnit.SECONDS.convert(
        1500, TimeUnit.MILLISECONDS);
```

`seconds == 1`, not `1.5`, because the result is an integer `long`.

Some utility methods:

- `TimeUnit.SECONDS.toMillis(5)` → `5000`.
- `TimeUnit.MILLISECONDS.toNanos(2)` → `2_000_000`.
- `TimeUnit.MINUTES.toSeconds(3)` → `180`.
- `TimeUnit.NANOSECONDS.toMillis(999_999)` → `0`.
- `TimeUnit.SECONDS.convert(1_999, TimeUnit.MILLISECONDS)` → `1`.

**There are no fractional units in a `long` result.** If you need to preserve nanosecond precision, keep the value in a sufficiently fine unit until you call the API that accepts the timeout.

### Example 1: Unit Conversion, Truncation, and Saturation

Create the file `TimeUnitConversionDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class TimeUnitConversionDemo {
    public static void main(String[] args) {
        System.out.println("3s to ms="
                + TimeUnit.SECONDS.toMillis(3));
        System.out.println("1500ms to s="
                + TimeUnit.SECONDS.convert(
                        1500, TimeUnit.MILLISECONDS));
        System.out.println("999999ns to ms="
                + TimeUnit.NANOSECONDS.toMillis(999_999));
        System.out.println("-1500ms to s="
                + TimeUnit.SECONDS.convert(
                        -1500, TimeUnit.MILLISECONDS));
        System.out.println("23h to days="
                + TimeUnit.DAYS.convert(
                        23, TimeUnit.HOURS));
        System.out.println("huge days to nanos="
                + TimeUnit.DAYS.toNanos(Long.MAX_VALUE));
    }
}
```

Compile/run with JDK 17+:

```bash
javac TimeUnitConversionDemo.java
java TimeUnitConversionDemo
```

Output:

```text
3s to ms=3000
1500ms to s=1
999999ns to ms=0
-1500ms to s=-1
23h to days=0
huge days to nanos=9223372036854775807
```

Explanation:

1. `3s` converted to ms is exact: `3000`.
2. `1500ms` converted to whole seconds becomes `1`, **losing the 500ms remainder**.
3. `999_999ns` is less than 1ms, so converting to milliseconds gives `0`.
4. `-1500ms` converted to whole seconds becomes `-1`: Java integer division rounds **toward 0**, not always toward negative infinity.
5. `23h` is less than a fixed 24-hour day, so `toDays` is `0`.
6. `Long.MAX_VALUE` days converted to nanoseconds exceeds the `long` range. `TimeUnit` returns a **saturated** value at `Long.MAX_VALUE`, rather than wrapping around to a negative number.

You should not take `toMillis(...) == 0` and conclude "there is no time left" if hundreds of thousands of nanoseconds still remain. **Too coarse a unit** erased the remainder during integer conversion.

## 4. Conversion Truncation: Cases That Cause Timeout Bugs

Suppose a deadline has only `800_000 ns` = `0.8 ms` remaining.

```java
long remainingNanos = 800_000;
long remainingMillis =
        TimeUnit.NANOSECONDS.toMillis(remainingNanos);
// remainingMillis == 0, even though remaining time is positive.
```

If the code checks `if (remainingMillis <= 0)`, it may reject a step that could still complete within `0.8ms`. If it calls the API:

```java
future.get(remainingMillis, TimeUnit.MILLISECONDS);
```

then `get(0, MILLISECONDS)` acts as an immediate poll rather than waiting `0.8ms`.

**How to preserve resolution:** pass the remaining time directly in nanoseconds:

```java
long nanos = budget.remainingNanos();
if (nanos <= 0) {
    throw new TimeoutException("budget exhausted");
}
return future.get(nanos, TimeUnit.NANOSECONDS);
```

This is an **illustrative snippet** inside a method with `budget`, `future`, `TimeoutException`, and appropriate checked exception declarations. Even when passing nanoseconds, **actual wakeup precision** still depends on the scheduler; the benefit is that you do not lose resolution **due to the unit conversion itself**.

### Be Careful with Negative Timeouts

Negative time values generally do not mean "wait negative one second." Many timeout APIs treat non-positive wait times as no wait, but each API's contract may differ. Do not rely on passing negative values to `Future.get`, `Condition.await`, or `Lock.tryLock` as a universal standard timeout mechanism.

Normalize at the boundary:

```java
long remaining = Math.max(0L, deadlineNanos - nowNanos);
```

This is illustrative code; raw subtraction must also consider overflow and the arbitrary origin of `System.nanoTime()`. Later sections build a calculation based on **elapsed time** that is safe for practical deadlines.

## 5. Integer Saturation and `long` Limits

`TimeUnit` uses `long`, and when converting to finer units, it **saturates** to `Long.MAX_VALUE` or `Long.MIN_VALUE` when the arithmetic would exceed the bounds. This is useful behavior because it avoids turning a huge timeout into a meaningless negative value.

For example:

```java
long nanos = TimeUnit.DAYS.toNanos(Long.MAX_VALUE);
// nanos == Long.MAX_VALUE
```

However, distinguish this from other arithmetic operations:

```java
long nanos = hugeSeconds * 1_000_000_000L;
```

The second line **does not saturate automatically**; `long` multiplication can overflow and wrap around. Prefer `TimeUnit.SECONDS.toNanos(hugeSeconds)` when the goal is simply unit conversion.

### Comparison with `java.time.Duration`

`Duration` represents a time span in seconds and nanoseconds with fine-grained resolution. It is well suited for configuration APIs, deadlines, logging, or general time handling.

```java
Duration duration = Duration.ofMillis(1500);
long nanos = duration.toNanos();
long millis = duration.toMillis();
```

This is an illustrative snippet, requiring `import java.time.Duration`. `nanos` is `1_500_000_000` and `millis` is `1500`.

Unlike `TimeUnit`, which applies saturation rules in its conversions, some `Duration` conversions such as `toNanos()` can throw `ArithmeticException` if the value cannot be represented in a `long`. **Do not assume the two APIs share the same overflow contract.**

When using `Duration` for user-supplied timeouts, validate that the value is **non-negative**, within system-allowed bounds, and will not overflow in the required conversion.

## 6. TimeUnit Is Not a Clock

A statement like:

```java
TimeUnit.MILLISECONDS.sleep(10);
```

requests the thread to sleep **for at least as long as the JVM/OS wait mechanism supports**, without guaranteeing that execution resumes at the exact `10ms` mark. After the time elapses, the thread still depends on when the scheduler runs it again.

Distinguish two concepts:

- **Representational resolution:** the smallest increment a type or unit can express; `NANOSECONDS` represents down to 1ns.
- **Runtime accuracy:** how close to the deadline an actual event occurs; this depends on the OS, JVM, timer resolution, machine load, GC pauses, contention, CPU scheduling, and API characteristics.

Choosing `TimeUnit.NANOSECONDS` does not mean the thread will wake up or a scheduled task will run with exact nanosecond accuracy.

In particular, `Thread.sleep`, `TimeUnit.sleep`, and some wait methods can be **interrupted**; these APIs can throw `InterruptedException`. When interrupted, handle the cancellation signal properly instead of using an empty catch block and looping forever.

### Three Utility APIs on TimeUnit

`TimeUnit` also provides:

```java
TimeUnit.MILLISECONDS.sleep(20);
TimeUnit.SECONDS.timedJoin(thread, 2);
TimeUnit.MILLISECONDS.timedWait(monitor, 200);
```

These are **independent illustrative snippets**. `thread` must be a valid `Thread`; for `timedWait`, the caller must hold **the monitor of `monitor` itself**, just as when calling `monitor.wait(...)`, otherwise an `IllegalMonitorStateException` may be thrown. Do not use `timedWait` as a substitute for a proper condition protocol. Wait conditions must be checked in a `while` loop due to spurious wakeups and the possibility that the condition changes by the time the thread wakes up.

## 7. Elapsed-Time Clock: `System.nanoTime()`

When calculating **remaining budget**, do not take two `System.currentTimeMillis()` readings and subtract them indiscriminately. The wall-clock can be adjusted by NTP, user clock changes, or system time updates.

`System.nanoTime()` is designed for **measuring elapsed time**. Its value has an arbitrary origin; it is **not a Unix timestamp**, carries no date or time, and can be negative.

Pattern:

```java
long startedAt = System.nanoTime();
// Perform a step.
long elapsed = System.nanoTime() - startedAt;
```

`elapsed` is the number of nanoseconds measured from the start point to the present. For reasonable intervals smaller than about `2^63 ns` (roughly 292 years), this subtraction is the standard Java idiom even when the `long` representation wraps around. Do not use a `nanoTime()` value as an absolute point in time to store in a database or compare across JVMs.

### Difference from `Instant`

- `Instant.now()`: a point on the wall clock, suitable for storing timestamps/logs when an event occurs.
- `System.nanoTime()`: measures duration/timeouts within the same JVM, suitable for computing an elapsed budget.
- `TimeUnit`: the **unit** of a time span; it does not provide a clock of its own.

You can log `Instant.now()` for humans while using `nanoTime()` to decide the deadline of a retry loop. Do not add a `nanoTime` value to epoch millis and assume both clocks share the same reference frame.

## 8. Shared Budget: Do Not Restart the Timeout for Each Step

Suppose a request has a **total budget of 500ms**, consisting of three steps:

1. Wait for a lock.
2. Wait for data to become ready.
3. Wait for a `Future` result.

**Wrong:** each step calls its API with the full `500ms`:

```java
lock.tryLock(500, TimeUnit.MILLISECONDS);
ready.await(500, TimeUnit.MILLISECONDS);
future.get(500, TimeUnit.MILLISECONDS);
```

This is a **budget anti-pattern**, setting aside unlocking, exceptions, and return values of each API. Each step could wait nearly `500ms`, pushing total latency close to **1500ms** plus overhead. The more steps there are, the further the end-to-end deadline stretches.

**Right idea:** have **one start time and one budget**, and recompute **remaining time** after each step:

```text
Total budget: 500ms
Start                   500ms remaining
Step 1 uses 300ms       200ms remaining
Step 2 uses 150ms        50ms remaining
Step 3 may use at most 50ms
At 500ms => do not start a new 500ms wait.
```

Do not rigidly split into 166ms per step unless there is a specific requirement: if one step finishes quickly, subsequent steps can use the unspent portion. This is an **end-to-end deadline**, not a static per-part timeout.

## 9. A TimeBudget Using Elapsed Time and LongSupplier

To test budget-splitting logic deterministically without relying on the scheduler, design a helper that accepts a **nanosecond clock** via `LongSupplier`. In production, pass `System::nanoTime`; in tests, use a fake clock that can be advanced at will.

Create the file `TimeBudgetDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class TimeBudgetDemo {
    static final class Budget {
        private final LongSupplier clock;
        private final long started;
        private final long allowedNanos;

        Budget(long timeout, TimeUnit unit, LongSupplier clock) {
            if (timeout < 0) {
                throw new IllegalArgumentException("negative timeout");
            }
            this.clock = clock;
            this.started = clock.getAsLong();
            this.allowedNanos = unit.toNanos(timeout);
        }

        long remainingNanos() {
            long elapsed = clock.getAsLong() - started;
            if (elapsed <= 0) {
                return allowedNanos;
            }
            return Math.max(0L, allowedNanos - elapsed);
        }

        long remainingMillis() {
            return TimeUnit.NANOSECONDS.toMillis(remainingNanos());
        }
    }

    public static void main(String[] args) {
        AtomicLong fakeNanos = new AtomicLong(0);
        Budget budget = new Budget(
                500, TimeUnit.MILLISECONDS, fakeNanos::get);

        System.out.println("at 0ms=" + budget.remainingMillis());

        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(300));
        System.out.println("at 300ms=" + budget.remainingMillis());

        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(150));
        System.out.println("at 450ms=" + budget.remainingMillis());

        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(60));
        System.out.println("at 510ms=" + budget.remainingMillis());
    }
}
```

```bash
javac TimeBudgetDemo.java
java TimeBudgetDemo
```

The output is completely deterministic:

```text
at 0ms=500
at 300ms=200
at 450ms=50
at 510ms=0
```

This example **does not sleep** and does not depend on machine performance. `AtomicLong` is used as a simulated clock to demonstrate the exact calculation.

**Using in production:** create `new Budget(timeout, unit, System::nanoTime)` and call `remainingNanos()` right before each wait step. Note that a test `LongSupplier` must advance in nanosecond units, and `nanoTime` subtraction assumes practical measurement intervals are far smaller than the huge `long` wraparound range (about 292 years).

**Do not use `remainingMillis() == 0` as the expiration condition:** it can be `0` even when `remainingNanos() > 0` due to truncation. Use nanos for expiration logic, and convert to ms only for **display**.

## 10. How Does the TimeBudget Helper Handle Overflow?

In the example, `unit.toNanos(timeout)` applies `TimeUnit` saturation when the amount is too large. `allowedNanos` can become `Long.MAX_VALUE` if the requested timeout exceeds nanosecond representation capacity. For normal finite budgets, this has no impact.

For real systems, enforce **reasonable timeout bounds** (such as a few seconds, minutes, or hours depending on the domain), instead of accepting `Long.MAX_VALUE` nanoseconds and inadvertently creating a virtually unbounded wait.

The calculation:

```java
long elapsed = System.nanoTime() - started;
long remaining = Math.max(0L, allowedNanos - elapsed);
```

is preferred over directly comparing two unchecked absolute `deadline` values. Even so, it still carries standard timing assumptions:

- The elapsed clock must be monotonic and not jump with wall-clock adjustments.
- Do not use the helper for multi-century durations that exceed the safe interpretation range of `long` differences.
- Do not mix `System.currentTimeMillis()` values into `System.nanoTime()` subtraction.
- When `0` remains, you can choose a fail-fast policy; results of already-completed steps do not vanish on their own.
- If unusually long delays are needed, manage them by calendar checkpoints and an appropriate scheduler/renewal mechanism rather than holding a single massive wait.

## 11. Passing the Remaining Budget to `Future.get()`

An important pattern for multi-step workflows:

```java
long remaining = budget.remainingNanos();
if (remaining <= 0) {
    throw new TimeoutException("request budget exhausted");
}
T result = future.get(remaining, TimeUnit.NANOSECONDS);
```

This is an **illustrative snippet** inside a generic method declaring checked exceptions; `budget` is the remaining-time helper and `future` is a `Future<T>`.

`Future.get(timeout, unit)` has distinct outcomes that must be separated:

- **Success:** returns `T`.
- **Task failed:** throws `ExecutionException`; inspect `getCause()`.
- **Future was cancelled:** throws `CancellationException`.
- **Caller thread was interrupted while waiting:** throws `InterruptedException`.
- **Did not complete before the wait timeout:** throws `TimeoutException`.

**Very important:** a `TimeoutException` from `Future.get(timeout)` **does not automatically cancel the task**. The task may keep running and continue consuming CPU/I/O. If the request policy wants to stop the task after the deadline, consider `future.cancel(true)` and understand that it is only a cooperative interrupt request.

### Example 3: Timeout Does Not Automatically Cancel the Task

Create the file `FutureWaitTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureWaitTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "DONE";
            });

            started.await();
            try {
                future.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("caller timeout");
            }

            System.out.println("cancelled=" + future.isCancelled());
            release.countDown();
            System.out.println("later=" + future.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac FutureWaitTimeoutDemo.java
java FutureWaitTimeoutDemo
```

Output when there is no unexpected interrupt:

```text
caller timeout
cancelled=false
later=DONE
```

The task signaled `started` and is waiting on `release`, which has not been opened yet; `get(30ms)` must time out because the task cannot complete. `isCancelled()` remains `false` because timing out **does not call cancel**. After releasing the latch, the task returns its result and the subsequent `get()` succeeds.

In real applications, do not call an **untimed** `future.get()` after an overall timeout if the SLA requires not waiting any longer. The example does so intentionally to prove that timeout **does not cancel**. For an end-to-end deadline, stop waiting or call `cancel(true)` according to policy.

## 12. Sharing One Budget Across Future, CountDownLatch, and Lock

Synchronization primitives have similar signatures but different return semantics:

```java
future.get(remaining, TimeUnit.NANOSECONDS);           // T or exception
latch.await(remaining, TimeUnit.NANOSECONDS);          // boolean
lock.tryLock(remaining, TimeUnit.NANOSECONDS);         // boolean
condition.await(remaining, TimeUnit.NANOSECONDS);      // boolean
executor.awaitTermination(remaining, TimeUnit.NANOSECONDS); // boolean
```

These are illustrative snippets; `remaining` must be **recomputed right before each call**, and variables must have the appropriate types. **Do not** compute remaining once and pass the same value repeatedly to every step.

Example realistic flow:

```text
Clock starts at t0; budget = 800ms.

Step A: latch.await(remainingNanos, NANOSECONDS)
          if false: request timeout
          if true:  recompute remaining

Step B: future.get(remainingNanos, NANOSECONDS)
          if TimeoutException: request timeout
          if ExecutionException: task failed
          if success: recompute remaining

Step C: lock.tryLock(remainingNanos, NANOSECONDS)
          if false: request timeout
          if true: run short critical section, unlock in finally
```

**Deadlock warning:** avoid holding a lock while waiting on a `Future` or latch if the awaited task **needs that same lock** to make progress. You can wait for the condition/data first and only lock at the end for a brief commit; ensure result invariants are preserved.

When a blocking step returns due to an **interrupt**, that signal is different from a timeout. For `InterruptedException`, propagate the exception or restore the interrupt flag if it cannot be propagated, and stop at a safe point. Do not "reset the budget" upon interruption and try to wait another full timeout.

## 13. Example 4: End-to-End Deadline with Two Wait Steps

The program below uses a single shared budget for **two latches**. Both are already open to demonstrate the success branch without depending on worker timing. The deadline calculation still uses the real `System.nanoTime()`.

Create the file `SharedDeadlineDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class SharedDeadlineDemo {
    static long remainingNanos(long startedAt, long budgetNanos) {
        long elapsed = System.nanoTime() - startedAt;
        return Math.max(0L, budgetNanos - elapsed);
    }

    static boolean awaitWithinBudget(
            CountDownLatch first,
            CountDownLatch second,
            long timeout,
            TimeUnit unit) throws InterruptedException {

        long startedAt = System.nanoTime();
        long budgetNanos = unit.toNanos(timeout);

        long remaining = remainingNanos(startedAt, budgetNanos);
        if (remaining <= 0
                || !first.await(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        remaining = remainingNanos(startedAt, budgetNanos);
        if (remaining <= 0
                || !second.await(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        return true;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch first = new CountDownLatch(0);
        CountDownLatch second = new CountDownLatch(0);

        boolean finished = awaitWithinBudget(
                first, second, 5, TimeUnit.SECONDS);
        System.out.println("finished=" + finished);
    }
}
```

```bash
javac SharedDeadlineDemo.java
java SharedDeadlineDemo
```

Output in a normal runtime environment when the two very short steps complete within five seconds:

```text
finished=true
```

Because both latches are already at `count=0`, `await` returns immediately. However, if the JVM is paused or delayed in scheduling long enough to **exceed the deadline between the two checks**, the result can be `false` according to policy. Do not fabricate guarantees that a program will always finish before a physical deadline simply because the normal operation is very fast.

**Key takeaway of the code:** `startedAt` and `budgetNanos` are created **once**. Each `await` receives the remaining time freshly computed from the same `startedAt`, rather than getting another full `5 seconds`.

## 14. Waiting for a Lock with a Time Budget: Ownership and `finally`

`ReentrantLock.tryLock(timeout, unit)` waits for a bounded duration, returns `true` when **the lock has been acquired**, returns `false` if the wait time expires without acquiring the lock, and can throw `InterruptedException` if interrupted.

Pattern:

```java
long remaining = budget.remainingNanos();
if (remaining <= 0) {
    throw new TimeoutException("no budget for lock");
}

if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("lock unavailable");
}
try {
    updateState();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet inside a method with an appropriate `throws` declaration. `unlock()` is called **only after `tryLock` returns `true`**. If it returns `false` or throws `InterruptedException`, the caller did not acquire the lock from that call, so it must not unlock unconditionally.

### Critical Section Latency Also Consumes the Budget

Even if the lock is acquired at 4.9 seconds into a 5-second budget, the subsequent work still takes time. `tryLock(timeout)` only bounds **the time spent waiting to acquire the lock**; it does not set a timer that forcibly terminates code inside the critical section.

If a strict end-to-end SLA is required, check `budget.remainingNanos()` before starting an operation and choose safe cancellation points. Never abort a multi-field update in a corrupted state just to meet a deadline; design atomic commit/rollback units instead.

## 15. `awaitTermination` Must Also Share the Shutdown Budget

An application may shut down an executor in two phases:

1. `shutdown()`, wait gracefully.
2. If not done, `shutdownNow()`, wait further.
3. If still not done, report incomplete termination.

If the caller has a **total deadline of 8 seconds**, do not pass `awaitTermination(8, SECONDS)` in both phases; the total could reach roughly 16 seconds.

A pattern using remaining time:

```java
long started = System.nanoTime();
long totalNanos = TimeUnit.SECONDS.toNanos(8);

executor.shutdown();
long remaining = Math.max(
        0L, totalNanos - (System.nanoTime() - started));

if (!executor.awaitTermination(remaining, TimeUnit.NANOSECONDS)) {
    executor.shutdownNow();

    remaining = Math.max(
            0L, totalNanos - (System.nanoTime() - started));

    boolean terminated = executor.awaitTermination(
            remaining, TimeUnit.NANOSECONDS);
    if (!terminated) {
        reportIncompleteShutdown();
    }
}
```

This is an **illustrative snippet** inside a method that handles `InterruptedException`, with `executor` and `reportIncompleteShutdown()` defined by the application.

**Note:** `shutdownNow()` is a best-effort cancellation request, typically interrupting workers. It does not force all tasks to stop immediately. When the deadline expires, report that shutdown is incomplete rather than assuming "because `awaitTermination` returned, workers must have stopped."

If the thread coordinating shutdown is interrupted while awaiting, the procedure may call `shutdownNow()` and restore the interrupt flag before exiting; that is a separate lifecycle decision, and the signal should not be swallowed.

## 16. Precision: Conversion, Clock, and Scheduler Are Three Separate Layers

Separate the three sources of discrepancy:

| Layer | Issue | Example |
| --- | --- | --- |
| **Conversion arithmetic** | Truncates fractional parts when converting to coarser units | 999,999ns → 0ms |
| **Elapsed clock** | Resolution/sampling cost of `nanoTime`, arbitrary origin | Two very close calls may be indistinguishable |
| **Scheduler and runtime** | Delayed thread scheduling, GC pauses, CPU contention, timer granularity | A 10ms timeout does not guarantee the callback runs at exactly 10ms |

Therefore, `TimeUnit.NANOSECONDS` is **the unit used to express a delay or timeout**, not a promise of nanosecond accuracy.

If a task needs to measure actual latency, use `System.nanoTime()` before and after and observe a distribution over many runs. Do not run a single `sleep(10)` and claim to know the JVM's timer accuracy.

## 17. Pitfall: Using `sleep` to "Wait for Completion"

`TimeUnit.MILLISECONDS.sleep(100)` may give other tasks a chance to run, but it does not guarantee a task has finished after 100ms. If you need to know an event has occurred, use a primitive that expresses that condition:

- `CountDownLatch.await(timeout, unit)` when waiting for a number of events to complete.
- `Future.get(timeout, unit)` when waiting for a task's outcome.
- `Condition.await(timeout, unit)` when waiting for a condition in a lock protocol.
- `ExecutorService.awaitTermination(timeout, unit)` when waiting for an entire executor to finish.
- `Thread.join(timeout)` or `TimeUnit.timedJoin` when waiting for a thread to terminate.

Similarly, in concurrency tests, do not `sleep(50)` and assume a worker has reached a specific line. Use a latch or barrier to establish preconditions; use timeouts only to **bound tests so they do not hang indefinitely**, not as a replacement for completion signals.

## 18. Computing a Deadline as Wait + Processing + Overhead

A request might consist of:

```text
Budget = 1000ms
  wait for lock               70ms
  query/cache lookup         400ms
  wait for another Future    450ms
  serialization/logging       90ms
Total                       1010ms -> overdue
```

If each step only bounds its own wait time without accounting for **CPU work, serialization, network processing, and overhead**, end-to-end latency will still exceed the SLA.

Compute remaining time from a **shared clock** right before each step and check it after significant processing sections. Even code that computes remaining time accurately cannot force a **blocking call that lacks timeout support** to stop at the exact deadline. For I/O, use APIs with connect/read/request deadlines; for CPU-bound tasks, check a cancellation token or interrupt flag at safe points; for operations requiring transactions, ensure consistent commit/rollback.

**A deadline is a coordination policy**, not a mechanism that automatically preempts all Java code when time runs out.

## 19. Distinguishing Timeout, Cancellation, and Interruption

These concepts are related but distinct:

- **Timeout:** a wait operation does not complete within the allowed time; the API may return `false`, `null`, or throw `TimeoutException` depending on its contract.
- **Cancellation:** a request that work no longer needs to continue; may be done via `Future.cancel(true)` or an application token.
- **Interruption:** a signal sent to a thread. Many blocking APIs respond with `InterruptedException`; code must cooperate.
- **Deadline:** the end point of the time budget for **an entire workflow** or unit of work.

Example:

```java
try {
    String result = future.get(remaining, TimeUnit.NANOSECONDS);
    return result;
} catch (TimeoutException e) {
    future.cancel(true); // Only if policy wants to request cancellation.
    throw e;
}
```

This is an illustrative snippet without full imports/context. `cancel(true)` attempts to interrupt the task; **it does not guarantee immediate cleanup** or that side effects are rolled back.

An `InterruptedException` in the caller thread calling `get()` does not by default mean **the worker failed**. Handle caller and task cancellation according to a clear protocol; if the interrupt cannot be propagated, restore it with `Thread.currentThread().interrupt()` before leaving the scope.

## 20. Propagating a Budget Across Services or Processes

`System.nanoTime()` has an arbitrary origin within a single JVM. **Do not send a raw `nanoTime` value as an absolute deadline to another machine** and expect the receiver to compare it against its own clock. They do not share the same reference frame.

When crossing process boundaries:

1. You can send the **remaining duration**, already reduced by the elapsed time on the sender side.
2. Or send a **wall-clock deadline**, with awareness of clock skew and timeout contracts.
3. On the receiving side, use the received budget to start a **local monotonic clock**.
4. Subtract transmission overhead and guard against latency/clock skew according to system requirements.
5. Only pass deadlines to APIs that support them; do not assume an HTTP or database client automatically inherits the caller's `TimeUnit`.

These are general principles of distributed deadlines; no framework is needed to understand them. For execution within a single JVM, taking one `nanoTime()` at the start is the simplest and most reliable approach for an elapsed deadline.

## 21. `ScheduledExecutorService`: Delay Is Not an Exact Timestamp

`ScheduledExecutorService.schedule(task, delay, unit)` expresses the **delay** before a task becomes eligible to execute:

```java
scheduler.schedule(
        () -> sendReminder(),
        200,
        TimeUnit.MILLISECONDS);
```

This is an illustrative snippet where `scheduler` is a `ScheduledExecutorService` and `sendReminder()` is defined. It **does not promise the callback will start after exactly 200.000000ms**; workers may be busy, CPU may be contended, or the JVM may pause.

`scheduleAtFixedRate` attempts to maintain relative period marks, while `scheduleWithFixedDelay` measures the delay after one execution completes. Both are subject to scheduler realities, task duration, and exceptions in periodic tasks. Do not assume `TimeUnit` gives you "exact absolute scheduling."

If you need to schedule by calendar time ("8:00 AM tomorrow in Hanoi"), compute the calendar/wall-clock target with `java.time` first, then convert it to a delay at scheduling time, handling time zones and clock changes appropriately. `TimeUnit.DAYS` is still just a fixed 24 hours.

## 22. Should a Time Budget Add Directly to `System.nanoTime()`?

A common pattern is:

```java
long deadline = System.nanoTime() + timeoutNanos;
long remaining = deadline - System.nanoTime();
```

This pattern can be correct **if you clearly understand overflow and timeout range limits**, but it is easily misused when:

- `timeoutNanos` has saturated to `Long.MAX_VALUE`.
- Code compares `System.nanoTime() >= deadline` using direct integer comparison without handling wraparound.
- A deadline created in one JVM is used in another JVM.
- The deadline is stored as a wall-clock timestamp.
- Two `System.nanoTime()` calls are far apart or duration arithmetic exceeds the safe representation range.

For general learning, **storing `startedAt` + `allowedNanos`, then computing `elapsed = now - startedAt` and `remaining = max(0, allowed - elapsed)`** is easier to explain and well suited for reasonable timeouts.

Do not use `System.currentTimeMillis()` to solve a "monotonic deadline" problem simply because the numbers are human-readable. The system clock can jump.

## 23. Verifying Correctness with Fake Clocks and Latches

### Testing Deadline Calculations

Use a fake clock like `TimeBudgetDemo`:

- At `0ms`, budget is `500ms`.
- After `300ms`, `200ms` remains.
- After another `150ms`, `50ms` remains.
- After another `60ms`, `0ms` remains.

No sleeping is required. Results do not depend on whether the machine is fast or slow.

### Testing Timeout of a Waiting API

Keep a `CountDownLatch` closed and verify `await(30, MILLISECONDS)` returns `false` because the latch cannot open before the timeout. Then open the latch and verify success. Handle the case where the test thread is interrupted.

### Testing the Distinction Between Timeout and Cancel

Use `FutureWaitTimeoutDemo` to verify `get(timeout)` throws `TimeoutException` while `isCancelled()` remains `false`; the task completes after the latch is released.

### Avoiding Flaky Tests

Do not assert "must be exactly 30ms" using `System.currentTimeMillis()` or require ultra-short scheduler guarantees. Use reasonable timeouts and verify **logical state**: timed out when preconditions could not complete, completed after the latch opened, interrupts were not lost, and the executor was cleaned up.

## 24. Common Pitfalls

### 24.1. Reversing Source and Target Order in `convert`

`TimeUnit.SECONDS.convert(5000, MILLISECONDS)` is `5` seconds, whereas `TimeUnit.MILLISECONDS.convert(5, SECONDS)` is `5000` milliseconds. Read it using the formula **target.convert(value, source)**.

### 24.2. Treating a Truncated Result as an Expired Deadline

`NANOSECONDS.toMillis(500_000) == 0` does not mean 500,000ns have expired. Check remaining time in nanoseconds.

### 24.3. Converting Large Durations via Manual Multiplication

`seconds * 1_000_000_000L` can overflow. Use `TimeUnit.SECONDS.toNanos(seconds)` if you want saturation rules; still validate that the timeout is valid for your domain.

### 24.4. Resetting the Timeout at Each Step

`get(1s)` followed by `tryLock(1s)` followed by `await(1s)` can consume up to 3s. Use **one budget** and recompute remaining time before each step.

### 24.5. Using Wall-Clock Time for Elapsed Timeouts

`System.currentTimeMillis()` can jump when the system adjusts the clock. `System.nanoTime()` is suited for measuring duration within a JVM.

### 24.6. Confusing Nanosecond Resolution with Scheduler Accuracy

Passing `NANOSECONDS` does not guarantee the thread wakes up to the exact nanosecond. A timeout is a bound on the API's wait logic, not an absolute execution SLA.

### 24.7. Assuming a Timed-Out Future Was Cancelled

`Future.get(timeout)` throws `TimeoutException`, but the task may keep running. Issue `cancel(true)` explicitly according to policy if you want to request stopping it.

### 24.8. Sleeping to Wait for a Condition

`sleep(100)` does not prove a task or condition has finished. Use `CountDownLatch`, `Future`, `Condition`, or an appropriate primitive.

### 24.9. Using `TimeUnit.DAYS` as a "Calendar Day"

A fixed 24-hour day is not every local day in a calendar with daylight saving transitions. Use `java.time` for calendar semantics.

### 24.10. Truncating to Milliseconds Too Early

If an API accepts `NANOSECONDS`, keep remaining time in nanos. When converting to a coarser unit, account for truncation and do not turn a small positive duration into "expired."

### 24.11. Not Releasing a Lock on Timeout/Exception

If `tryLock` succeeds, always use `finally` to call `unlock()`. If it fails or is interrupted before acquiring the lock, do not call unlock unconditionally.

### 24.12. Believing a Deadline Helper Can Stop Any I/O

An elapsed budget only provides **the remaining value**. If a downstream API does not support timeouts or cancellation, a deadline cannot preempt that call on its own.

## 25. Self-Check Questions

**Q1.** What does `TimeUnit.SECONDS.convert(1_999, TimeUnit.MILLISECONDS)` return?

**Answer:** `1`; the 999ms remainder is truncated when converting to whole seconds.

**Q2.** `TimeUnit.NANOSECONDS.toMillis(999_999)` equals 0. Is the time expired?

**Answer:** Not necessarily; 999,999 nanoseconds still remain. Check in a sufficiently fine unit.

**Q3.** Does `TimeUnit.DAYS.toNanos(Long.MAX_VALUE)` wrap around to a negative number?

**Answer:** No. `TimeUnit` conversions saturate at `Long.MAX_VALUE` when exceeding the limit.

**Q4.** A workflow has a 500ms budget, and step A uses 300ms. How much time may step B use at most?

**Answer:** Roughly the 200ms remaining (minus actual overhead), rather than resetting to 500ms.

**Q5.** Why not use `Instant.now()` or `System.currentTimeMillis()` to measure monotonic wait time?

**Answer:** Wall-clock time can be adjusted; `System.nanoTime()` is suited for measuring elapsed duration within the same JVM.

**Q6.** `future.get(100, MILLISECONDS)` throws `TimeoutException`. Is the worker cancelled?

**Answer:** Not automatically. The task may still be running; cancellation is a separate request.

**Q7.** Does `TimeUnit.NANOSECONDS.sleep(1)` guarantee code wakes up after exactly 1ns?

**Answer:** No. Representational resolution does not mean actual wakeup accuracy.

**Q8.** If `lock.tryLock` returns `false`, should `lock.unlock()` be called?

**Answer:** No, because the thread did not acquire the lock from that call. Only unlock after a successful acquisition.

**Q9.** Does `awaitTermination(timeout)` returning `false` mean the executor has stopped?

**Answer:** It has not reached the terminated state within the wait time; workers may still be running.

**Q10.** Should you send an absolute `System.nanoTime()` value over the network for another server to use as a deadline timestamp?

**Answer:** No. `nanoTime` has an arbitrary origin and is not comparable across JVMs. Send the remaining duration or a wall-clock deadline with a clear contract.

**Q11.** When applying one budget to both `CountDownLatch.await` and `Future.get`, why must remaining time be recomputed?

**Answer:** Because waiting on the latch already consumed part of the budget. Reusing the initial timeout can cause total latency to exceed the budget.

**Q12.** To properly test 500ms budget logic, do you need a real `Thread.sleep(300)`?

**Answer:** No. An injected fake clock can simulate elapsed time accurately, avoiding flaky tests caused by the scheduler.

## 26. Summary

**`TimeUnit` expresses the time unit for conversions and timeout APIs, but it is not a clock and does not guarantee scheduling precision.** When converting to coarser units, `long` values are truncated; when converting overly large values to finer units, they can saturate. Do not equate `0ms` after conversion with `0ns` remaining.

To manage **a multi-step time budget**, start an elapsed clock with `System.nanoTime()`, maintain a single shared budget, **recompute `remainingNanos()` right before each waiting API call**, handle timeout/interrupt/cancel separately, and never reset the deadline at each step. `Future.get`, `CountDownLatch.await`, `Lock.tryLock`, and `ExecutorService.awaitTermination` only bound the wait portion of the call itself; other CPU/I/O work still consumes the shared time.

In Java concurrency, a proper deadline is an **end-to-end protocol**, not a list of calls each given its own independent timeout. Test with fake clocks and latches, preserve consistency on cancellation, and use `java.time` types for calendar points in time rather than confusing them with elapsed-time measurements.
