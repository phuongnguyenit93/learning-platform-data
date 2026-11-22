# `System.nanoTime()` for Measuring Elapsed Time and Limitations of the System Clock

## 1. "What time is it now?" vs. "How much time has elapsed?"

A log needs to record when an event occurred; a network operation needs to know whether its timeout has been reached. Both questions involve time, yet they require different sources and different usage patterns.

- For a point in time that can be stored, displayed, or compared against a calendar date, an `Instant` from an appropriate `Clock` is typically used.
- For elapsed time within the same JVM process, use the difference between two `System.nanoTime()` calls.

`System.nanoTime()` does not return "the number of nanoseconds since 1970". It reads the JVM's high-resolution time source, with a fixed but arbitrary origin. The meaning lies in the **difference between two readings**, as specified in [Java SE 21 — System.nanoTime()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

```java
// Illustrated inside a method; doWork is a defined task.
long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;
```

The magnitude or sign of `start` alone does not indicate a year, date, or hour. Do not pass it directly to `Instant.ofEpochSecond()`/`ofEpochMilli()` and treat the result as the timestamp of the operation.

## 2. Why not use the wall-clock for every measurement?

`System.currentTimeMillis()` is anchored to the 1970 UTC epoch and uses milliseconds. `Instant.now()` provides the system instant in the date-time API. They are suitable for calendar timestamps, but the system time source can be affected by clock adjustments.

The [Java SE 21 — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) specification does not require every clock source in the date-time API to advance uniformly, monotonically, or with sub-second accuracy. Therefore, you should not assume that every subsequent system-time reading increases by the exact elapsed time.

Suppose a wall-clock source returns 10,000 milliseconds and is then adjusted back to 9,500. The difference between the two numbers is -500, even though the second observation occurred after the first. This example only simulates the limitation of taking wall-clock differences; it does not actually alter the machine's clock.

`Duration.between(startInstant, endInstant)` still computes the exact interval between **the two given values**. It cannot repair the quality or monotonicity of the source that produced those two values. Elapsed-time measurement and timestamping should be chosen according to their purpose, rather than renaming variables and treating the sources as equivalent.

## 3. How to measure and keep the right units

The basic pattern is to capture a mark before the work, capture a mark after, and subtract:

```java
static long measureNanos(Runnable action) {
    long start = System.nanoTime();
    action.run();
    return System.nanoTime() - start;
}
```

This method returns the elapsed nanoseconds of a normally completed call. If `action.run()` throws an exception, it does not return a measurement; if you need to record duration even on failure, place the recording logic in a `finally` block while preserving the original exception-handling semantics.

The result includes time the operation spent waiting, being preempted so other threads could run, or encountering runtime activity during the measurement interval. It is not the dedicated CPU time used by the thread alone. Asynchronous tasks also require identifying the right completion point: measuring the time to submit a task is not the same as measuring until that task finishes.

You can convert the measured difference with `Duration.ofNanos(elapsedNanos)`, or convert to another unit on output. Do not compare nanoseconds against a constant intended as milliseconds. If you perform integer division by `1_000_000`, any fraction smaller than one millisecond is truncated in the integer result; that does not mean the operation actually took 0 nanoseconds.

## 4. Comparing timeouts by difference, not by adding the deadline and comparing marks

For a non-negative timeout, the recommended pattern is:

```java
if (System.nanoTime() - start >= timeoutNanos) {
    // Reached or exceeded the timeout.
}
```

An error-prone pattern is:

```java
if (System.nanoTime() >= start + timeoutNanos) {
    // Do not use this pattern for timeout handling with nanoTime.
}
```

The addition `start + timeoutNanos` can overflow `long`, flipping the deadline to the opposite sign and making direct comparison wrong. When taking the difference properly, a single wrap across the counter's representation boundary still yields the correct small interval, provided the actual interval under consideration is less than `2^63` nanoseconds (about 292 years). Do not overgeneralize this rule into a promise to handle arbitrarily long intervals.

Timeouts also need range validation. `Duration.toNanos()` can throw `ArithmeticException` when the value is too large to be represented as a `long`. Do not silently turn an overflowed value into a negative timeout or an already-expired deadline.

## 5. Program verifying timeouts and counter wraparound

Save the code to `NanoTimeDemo.java`. The program uses Java 17 or later and requires no external libraries.

`measureNanos()` demonstrates real measurement with `System.nanoTime()`. The `main` method tests the timeout algorithm using a controlled counter source so stdout does not depend on machine speed. The simulated counter ticks are in nanoseconds; they are not presented as real hardware measurements.

```java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class NanoTimeDemo {
    static long measureNanos(Runnable action) {
        long start = System.nanoTime();
        action.run();
        return System.nanoTime() - start;
    }

    static final class NanoTimeout {
        private final LongSupplier source;
        private final long start;
        private final long timeoutNanos;

        NanoTimeout(Duration timeout, LongSupplier source) {
            Objects.requireNonNull(timeout);
            if (timeout.isNegative()) {
                throw new IllegalArgumentException("negative timeout");
            }
            this.timeoutNanos = timeout.toNanos();
            this.source = Objects.requireNonNull(source);
            this.start = source.getAsLong();
        }

        long elapsedNanos() {
            return source.getAsLong() - start;
        }

        boolean expired() {
            return elapsedNanos() >= timeoutNanos;
        }
    }

    private static void expect(boolean expected, boolean actual, String label) {
        if (expected != actual) {
            throw new AssertionError(label);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        AtomicLong ticks = new AtomicLong(1_000);
        NanoTimeout timer = new NanoTimeout(Duration.ofNanos(500), ticks::get);
        expect(false, timer.expired(), "initially expired");
        ticks.set(1_499);
        expect(false, timer.expired(), "before boundary");
        ticks.set(1_500);
        expect(true, timer.expired(), "at boundary");
        ticks.set(1_750);
        System.out.println("elapsed nanos = " + timer.elapsedNanos());

        long startNearWrap = Long.MAX_VALUE - 4;
        ticks.set(startNearWrap);
        NanoTimeout wrapped = new NanoTimeout(Duration.ofNanos(8), ticks::get);
        expect(false, wrapped.expired(), "near wrap initially");
        ticks.set(startNearWrap + 7);
        expect(false, wrapped.expired(), "near wrap before boundary");
        ticks.set(startNearWrap + 8);
        expect(true, wrapped.expired(), "near wrap at boundary");
        System.out.println("wrapped elapsed nanos = " + wrapped.elapsedNanos());

        long wallBefore = 10_000;
        long wallAfter = 9_500;
        System.out.println("simulated wall-clock delta = "
                + (wallAfter - wallBefore));
        System.out.println("all checks passed");
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NanoTimeDemo.java
java NanoTimeDemo
```

Output:

```text
initially expired = false
before boundary = false
at boundary = true
elapsed nanos = 750
near wrap initially = false
near wrap before boundary = false
near wrap at boundary = true
wrapped elapsed nanos = 8
simulated wall-clock delta = -500
all checks passed
```

Failed expectations throw `AssertionError`, regardless of the `-ea` flag.

## 6. Reading the verification points from the example

### Before the deadline and at the deadline are two distinct cases

The counter starts at 1,000 and the timeout is 500 nanoseconds. At tick 1,499, the difference is 499, so it has not expired. At 1,500, the difference is exactly 500, so it has expired under the `>=` contract.

When the counter is 1,750, `elapsedNanos()` returns 750. That is an elapsed interval, not a calendar timestamp. The same source must be used for both the initial mark and subsequent readings.

### Crossing the `long` boundary does not mean time went backward

The second experiment starts at `Long.MAX_VALUE - 4`. Adding 7 and 8 in the code intentionally simulates the counter wrapping past the representation limit of `long`. Subtracting the initial mark still yields 7 or 8, so the timeout condition behaves correctly at the boundary.

This is also why the sign of a `nanoTime()` value must not be treated as an error indicator. The origin is arbitrary, and an individual reading can be negative. Do not apply `Math.abs()` to marks before subtracting, as doing so breaks the distance relationship you need to preserve.

### Testing a counter source does not require `Clock.fixed()`

`NanoTimeout` accepts a `LongSupplier` to read ticks. In production, you can instantiate it in the same scope as follows:

```java
NanoTimeout timeout = new NanoTimeout(
        Duration.ofMillis(200), System::nanoTime);
```

In tests, `ticks::get` lets you set the counter before, at, and after the deadline without actually waiting. `AtomicLong` here merely holds the tick count to drive the example; the program is not verifying a concurrent scheduling algorithm.

`Clock.fixed()` controls readings based on that clock; it does not intercept or replace `System.nanoTime()`. If code needs both calendar timestamps and elapsed intervals, you can pass two sources with separate roles instead of assuming one test clock will control both.

## 7. Precision, resolution, and scope of use

Nanosecond units can represent very small intervals, but there is no guarantee that the source value changes every nanosecond. Two consecutive readings can be equal. Do not turn the width of the numeric type or the name `nanoTime` into a guarantee of one-nanosecond measurement accuracy on every machine.

The origin is only consistent within the same JVM. Do not persist an absolute tick count to a database for use after an application restart, do not compare tick counts from two JVMs, and do not send one to another machine to subtract directly from the receiver's tick count. If you need to store events for cross-system correlation, use a timestamp with an appropriate contract; if you need to store duration statistics, store the **computed difference** together with its unit.

A single short measurement is also not enough to conclude the steady-state speed of a Java snippet. Runtime startup, JIT compilation, dead-code elimination, caches, and scheduling noise can all affect the result. The `measureNanos()` method is a difference-taking pattern, not a full benchmarking harness.

## 8. Keeping measurement responsibilities clear

A timeout check only tells you that the threshold has been reached when the program checks it. It does not automatically stop a thread, cancel a network call, or guarantee that work finishes at the exact boundary nanosecond. Waiting and cancellation mechanisms should be wired into the timeout rules of the operation's API; avoid busy-wait loops that do nothing but repeatedly read the clock.

When a requirement genuinely says "expires at 10:00 UTC", that is a calendar-time deadline and should be modeled accordingly. When a requirement says "wait at most 200 milliseconds from the start", that is a local elapsed interval suited to the counter source in this article. Both kinds of deadlines can coexist in one system, but their arithmetic should not be mixed.

Exercise: in the first simulation, add a tick at 1,501; `expired()` still returns `true`. Next, set the timeout to 0 and explain why the very first check is already expired under the `>=` relation. Finally, show why replacing `source.getAsLong() - start` with comparing the current mark against `start + timeoutNanos` breaks the near-`long`-limit case even though small examples still appear to work.
