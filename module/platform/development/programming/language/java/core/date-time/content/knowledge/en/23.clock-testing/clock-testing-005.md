# Clock.offset() and Clock.tick()

## 1. Two Ways to Transform Time Readings

When testing a feature that depends on “now”, sometimes you need to see a time 90 minutes later than the base source. Other times, you want the source to expose only whole-second boundaries, without fractional nanoseconds.

`Clock.offset` and `Clock.tick` serve two different needs:

| Method | Effect on the instant from the base clock | Example |
|---|---|---|
| `Clock.offset(base, duration)` | Adds a fixed amount of time | Shift 90 minutes into the future |
| `Clock.tick(base, duration)` | Truncates down to the boundary of the chosen time step | Read only whole-second boundaries |

Both return a `Clock`, so they can be passed into `Instant.now(clock)`, `LocalDate.now(clock)`, or a class that already accepts a clock. They do not modify the system clock and do not automatically replace the clock for parts of the code that still call the no-argument `now()`.

## 2. Clock.offset: Adding a Fixed Shift to the Source

Syntax:

```java
Clock shifted = Clock.offset(base, Duration.ofMinutes(90));
```

This is an illustrative declaration using an existing `base` variable. Each time the resulting clock is read, the instant is obtained from the base clock and the offset is added.

If the base returns `2026-10-25T12:34:56Z`, an offset of +90 minutes yields `2026-10-25T14:04:56Z`. A negative offset of 5 minutes yields `2026-10-25T12:29:56Z`.

Properties to remember:

- `Duration` can be positive, negative, or zero.
- A zero offset does not change the result, and the API may return the base clock itself.
- The time zone of the offset clock is preserved from the base clock.
- The original clock is not mutated by creating an offset clock.
- If the base follows the system clock, the offset source also follows the base; if the base is fixed, the shifted result is also fixed.

### A Clock Offset Is Not a ZoneOffset

`Clock.offset` changes the **reported instant**. `withZone` changes the **time zone used to interpret the instant** without actively adding an amount to the timeline.

Adding 7 hours with `Clock.offset` is not the way to convert the same instant to Vietnam time: it creates a different instant. If you need the Vietnam date/time at the same instant, use the appropriate `ZoneId` and convert through the time zone.

Similarly, `Duration.ofDays(1)` is 24 hours of elapsed time, not the rule of “same local time tomorrow” in every time zone with DST. When a requirement is based on calendar days, you need to calculate using the appropriate type and time zone instead of using an offset as an implicit substitute.

### Not a “Run Faster” Command

An offset of +90 minutes does not make the clock run at double speed. It only maintains a fixed shift relative to the base. Calling `offset` also does not make the base advance to a new point in time on its own.

If you want to test a feature at multiple points in time, you can create clocks based on the same fixed source and pass them in one by one. There is no need to wait 90 minutes in real life to see future results.

## 3. Clock.tick: Truncating the Observable Resolution

Example:

```java
Clock wholeSeconds = Clock.tick(base, Duration.ofSeconds(1));
```

With a source of `12:34:56.789123456Z`, the result is `12:34:56Z`. This is **truncation (rounding down)**, not rounding to the nearest boundary by distance: even though the fraction is closer to second 57, the result is still at the start of second 56.

| Base source | Tick step | Result |
|---|---|---|
| `12:34:56.789123456Z` | 1 second | `12:34:56Z` |
| `12:34:56.789123456Z` | 250 milliseconds | `12:34:56.750Z` |
| `12:34:56.789123456Z` | 1 minute | `12:34:00Z` |

Multiple reads within the same tick interval may return the same value. That is the purpose of this clock, not a bug where the time source is stuck.

Tick boundaries are tied to how instants are truncated, not to the moment you create the object. Creating a clock at second 56.789 with a 1-second step does not mean subsequent jumps will occur at 57.789, 58.789.

### Not a Scheduler

`tick` does not spawn a background thread to run a task every second, does not invoke callbacks, and does not `sleep` waiting for the next boundary. It simply provides a way to read instants with a larger observation step.

If the base is `Clock.fixed`, wrapping it with `tick` still does not make the source advance on its own. Every time you query the same fixed base, you still receive the truncated boundary of that same instant.

To schedule tasks, you need a scheduler; to test a sequence of timestamps, you need a controllably advancing source or multiple fixed clocks. Do not use `tick` expecting that the number of `instant()` calls will advance time by one step.

## 4. Choosing a Valid tickDuration

Not every nanosecond length is accepted. According to the `Clock.tick` contract:

- Negative durations are rejected with `IllegalArgumentException`.
- A duration of 0 or 1 nanosecond has no truncation effect; it returns the base clock per the API contract.
- Whole multiples of milliseconds, such as 1 ms, 250 ms, 1 second, or 1 minute, are common valid choices.
- If the duration has a sub-millisecond fraction, its length must evenly divide one second in nanoseconds, with no remainder. For example, 20 ns or 500,000 ns satisfy the condition; 3 ns does not.

A duration that is too large can also cause an `ArithmeticException` when it cannot be represented in the required number of nanoseconds. Choose the duration according to practical needs and handle invalid configuration where the time source is constructed.

There are convenience methods that use the system source:

```java
Clock seconds = Clock.tickSeconds(zone);
Clock minutes = Clock.tickMinutes(zone);
Clock millis = Clock.tickMillis(zone);
```

These snippets assume `zone` is an already chosen `ZoneId`. They are convenient for the system source; when testing and you want to preserve a specific base source, use `tick(base, duration)` so you do not accidentally fall back to reading real time.

## 5. The Order of offset and tick Can Change the Result

The two transformations are not always commutative. With a base of `12:34:56.789123456Z`, an offset of 1.5 seconds, and a tick step of 1 second:

```text
offset then tick:
12:34:56.789123456
    + 1.5 seconds -> 12:34:58.289123456
    truncate sec  -> 12:34:58

tick then offset:
12:34:56.789123456
    truncate sec  -> 12:34:56
    + 1.5 seconds -> 12:34:57.500
```

If the contract requires the output to always be whole seconds, applying offset **after** tick can reintroduce a fractional part. Name or structure nested calls clearly to express the final rule.

Do not use the fact that both orders happen to produce the same result with whole-second offsets as proof that they are always equivalent. Tests should include an offset that is not a multiple of the tick step.

## 6. Complete Runnable Program

Save the following code to `OffsetAndTickDemo.java`. The program uses Java 17 or later and requires no external libraries. The entire base source is fixed so the output does not depend on when it is run.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class OffsetAndTickDemo {
    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2026-10-25T12:34:56.789123456Z"),
                ZoneOffset.UTC);

        System.out.println("base=" + base.instant());
        System.out.println("plus90Minutes="
                + Clock.offset(base, Duration.ofMinutes(90)).instant());
        System.out.println("minus5Minutes="
                + Clock.offset(base, Duration.ofMinutes(-5)).instant());
        System.out.println("offsetZone="
                + Clock.offset(base, Duration.ofHours(1)).getZone());

        Clock seconds = Clock.tick(base, Duration.ofSeconds(1));
        System.out.println("tickSecond=" + seconds.instant());
        System.out.println("tick250ms="
                + Clock.tick(base, Duration.ofMillis(250)).instant());
        System.out.println("tickMinute="
                + Clock.tick(base, Duration.ofMinutes(1)).instant());
        System.out.println("tickSecondAgain=" + seconds.instant());

        Duration shift = Duration.ofMillis(1500);
        Clock offsetThenTick = Clock.tick(
                Clock.offset(base, shift), Duration.ofSeconds(1));
        Clock tickThenOffset = Clock.offset(
                Clock.tick(base, Duration.ofSeconds(1)), shift);
        System.out.println("offsetThenTick=" + offsetThenTick.instant());
        System.out.println("tickThenOffset=" + tickThenOffset.instant());

        for (String text : new String[]{
                "2026-10-25T12:34:56.100Z",
                "2026-10-25T12:34:56.999999999Z",
                "2026-10-25T12:34:57Z"
        }) {
            Clock sample = Clock.fixed(Instant.parse(text), ZoneOffset.UTC);
            System.out.println("boundary=" + Clock.tick(
                    sample, Duration.ofSeconds(1)).instant());
        }

        System.out.println("zeroTick="
                + Clock.tick(base, Duration.ZERO).instant());
        System.out.println("oneNanoTick="
                + Clock.tick(base, Duration.ofNanos(1)).instant());

        try {
            Clock.tick(base, Duration.ofNanos(3));
        } catch (IllegalArgumentException e) {
            System.out.println("invalid3ns=IllegalArgumentException");
        }
        try {
            Clock.tick(base, Duration.ofSeconds(-1));
        } catch (IllegalArgumentException e) {
            System.out.println("negativeTick=IllegalArgumentException");
        }
    }
}
```

Compile and run:

```shell
javac OffsetAndTickDemo.java
java OffsetAndTickDemo
```

Expected output:

```text
base=2026-10-25T12:34:56.789123456Z
plus90Minutes=2026-10-25T14:04:56.789123456Z
minus5Minutes=2026-10-25T12:29:56.789123456Z
offsetZone=Z
tickSecond=2026-10-25T12:34:56Z
tick250ms=2026-10-25T12:34:56.750Z
tickMinute=2026-10-25T12:34:00Z
tickSecondAgain=2026-10-25T12:34:56Z
offsetThenTick=2026-10-25T12:34:58Z
tickThenOffset=2026-10-25T12:34:57.500Z
boundary=2026-10-25T12:34:56Z
boundary=2026-10-25T12:34:56Z
boundary=2026-10-25T12:34:57Z
zeroTick=2026-10-25T12:34:56.789123456Z
oneNanoTick=2026-10-25T12:34:56.789123456Z
invalid3ns=IllegalArgumentException
negativeTick=IllegalArgumentException
```

The `boundary` lines use three separate fixed sources, not one clock that automatically advances:

1. Second 56.100 is truncated down to the start of second 56.
2. Right before second 57, it still returns the start of second 56.
3. Exactly at the start of second 57, it returns second 57.

The `tickSecondAgain` line repeats the same value because the base does not change. The `offsetZone=Z` line confirms that a one-hour offset does not turn the UTC time zone into `+01:00`.

The exception names on the last lines are labels printed by the program when catching invalid configurations, not the full JDK message.

## 7. Limitations When Used with System Sources

### Tick Does Not Make the Source More Accurate

If the base clock is wrong or adjusted, tick only transforms the provided value. It does not synchronize the time and does not guarantee monotonicity so that readings always increase. Offset also only adds a shift; it does not fix the root cause of an inaccurate source.

Tick implementations may use caching for optimization. Boundary changes observed through a tick clock may appear later than when reading the base source directly. Do not build real-time tests based on the assumption that tick boundaries are always visible instantaneously.

### Reducing Resolution Can Affect Expiration Conditions

If a check requires an exact instant but the source is truncated to the minute, it may continue seeing an old boundary throughout that minute. Choose tick as part of the time contract, not merely as a way to make printed strings look cleaner.

If you only want to display without fractional parts, you can use a formatter at the presentation boundary while keeping the full `Instant` for the algorithm. Reducing the resolution of the source is a broader decision than changing how it is printed.

### Separate Reads Are Still Separate Reads

With a live running source, reading base and then reading offset or tick afterward may allow additional time to elapse between the two calls. Do not assert that the difference is always exact to the nanosecond using two consecutive reads. Use a fixed source when verifying transformation formulas, as in the program above.

## 8. Hands-On Practice

1. Change the offset in the composition section from 1,500 ms to 1,000 ms. Observe that both orders give the same result in this case, then explain why this does not refute the 1.5-second offset example.
2. Change the fractional part of the source to `.249999999` and `.250000000`, keeping the 250 ms step. Compare the two truncated boundaries right before and right at the boundary.
3. Keep the source fixed and call tick multiple times. Verify that the number of calls does not advance the boundary; eliminate the misconception that tick is a test step counter.
4. Create a +24-hour offset clock and compare it with only calling `withZone` on the original source. Point out which operation changes the `Instant` and which changes how the local date/time is determined.

Reference: [Clock — offset, tick, and utility methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) in Java SE 21.