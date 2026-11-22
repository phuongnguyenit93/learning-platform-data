# `Clock.fixed()` to Fix a Point in Time for Testing

## 1. Fixing the “Current” Time Source Instead of Waiting for Real Time

Suppose a registration portal closes starting on `2026-01-01` Vietnam time. To test right before and at the exact start of the closing day, there is no need to wait until New Year's Eve or change the system clock. You can provide the business logic with a `Clock` whose every read returns the chosen instant.

`Clock.fixed(fixedInstant, zone)` creates such a clock. According to [Java SE 21 — Clock.fixed()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId)), the clock always returns the same `Instant`; it is suitable when you need to observe a controllable point in time in tests.

The two arguments serve different roles:

- `fixedInstant`: the instant fixed on the timeline.
- `zone`: the time zone used to interpret that instant as a local date and time when needed.

```java
// Illustrated within a method.
Clock clock = Clock.fixed(
        Instant.parse("2025-12-31T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

The instant above is 17:00 UTC, but it is already 00:00 on `2026-01-01` in the chosen zone. The `zone` argument does not add seven hours to the `Instant` held internally; it provides the context for deriving the local date and time.

## 2. How to Read from a Fixed Clock

| Need | How to read | Does the result depend on the clock's zone? |
| --- | --- | --- |
| Instant on the timeline | `clock.instant()` or `Instant.now(clock)` | `Instant` itself does not vary by zone |
| Local date | `LocalDate.now(clock)` | Yes |
| Local time | `LocalTime.now(clock)` | Yes |
| Local date-time | `LocalDateTime.now(clock)` | Yes |
| Date-time with zone | `ZonedDateTime.now(clock)` | Yes |

The overloads accepting a `Clock` obtain the time source from the supplied object. For example, [LocalDateTime.now(Clock)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html#now(java.time.Clock)) creates a date-time from that clock; the resulting `LocalDateTime` value still does not store a zone in its type.

Creating a `Clock.fixed(...)` variable does not affect places that still call the no-argument `Instant.now()` or `LocalDate.now()`. For a test to control the point in time, the code under test must accept and use that clock.

## 3. Preparing a Meaningful Test

Before creating a clock, determine three things:

1. Is the rule comparing an instant or a local date?
2. If by date, which business time zone is used?
3. Is the boundary point included in the valid range?

In the example, registration remains open if the observed date is **before** the closing date. The closing date is `2026-01-01`; starting right at the beginning of that day, it is no longer open. Therefore, the program checks two points in time in Vietnam time:

| Point in time | Corresponding UTC instant | Expected |
| --- | --- | --- |
| `2025-12-31 23:59:59.999999999` | `2025-12-31T16:59:59.999999999Z` | Still open |
| `2026-01-01 00:00` | `2025-12-31T17:00:00Z` | Closed |

Choosing two `Instant` values one nanosecond apart tests the exact boundary in the data model. It does not require the physical clock or operating system to actually have nanosecond resolution.

## 4. Complete Runnable Program

Save the code to `FixedClockDemo.java`. The program uses Java 17 or later and requires no JUnit or external libraries. The `expect()` method throws `AssertionError` directly if the result is wrong, so it does not depend on the `-ea` flag:

```java
import java.time.*;
import java.util.Objects;

public class FixedClockDemo {
    static final class RegistrationWindow {
        private final Clock clock;

        RegistrationWindow(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        boolean isOpenUntil(LocalDate closingDate) {
            LocalDate observedDate = LocalDate.now(clock);
            return observedDate.isBefore(closingDate);
        }
    }

    private static void expect(boolean expected, boolean actual, String label) {
        if (expected != actual) {
            throw new AssertionError(label + ": expected " + expected
                    + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant midnight = Instant.parse("2025-12-31T17:00:00Z");
        Clock before = Clock.fixed(midnight.minusNanos(1), businessZone);
        Clock atBoundary = Clock.fixed(midnight, businessZone);

        System.out.println("before instant = " + Instant.now(before));
        System.out.println("before local = " + LocalDateTime.now(before));
        System.out.println("boundary instant = " + Instant.now(atBoundary));
        System.out.println("boundary local = " + LocalDateTime.now(atBoundary));

        LocalDate closingDate = LocalDate.of(2026, 1, 1);
        expect(true, new RegistrationWindow(before)
                .isOpenUntil(closingDate), "before closing day");
        expect(false, new RegistrationWindow(atBoundary)
                .isOpenUntil(closingDate), "at closing day");

        Clock utcView = atBoundary.withZone(ZoneOffset.UTC);
        System.out.println("UTC view date = " + LocalDate.now(utcView));
        System.out.println("original view date = " + LocalDate.now(atBoundary));
        expect(true, utcView.instant().equals(atBoundary.instant()),
                "same frozen instant");

        Instant first = before.instant();
        for (int i = 0; i < 1000; i++) {
            if (!first.equals(before.instant())) {
                throw new AssertionError("fixed clock changed");
            }
        }
        System.out.println("all fixed reads unchanged");
        System.out.println("all checks passed");
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 FixedClockDemo.java
java FixedClockDemo
```

Output:

```text
before instant = 2025-12-31T16:59:59.999999999Z
before local = 2025-12-31T23:59:59.999999999
boundary instant = 2025-12-31T17:00:00Z
boundary local = 2026-01-01T00:00
before closing day = true
at closing day = false
UTC view date = 2025-12-31
original view date = 2026-01-01
same frozen instant = true
all fixed reads unchanged
all checks passed
```

The points in time are constructed from explicit strings and an explicit zone, so the output does not depend on the date the program is run or the machine's default time zone.

## 5. How Does the Clock Enter the Business Logic?

`RegistrationWindow` accepts a `Clock` in its constructor, stores it in a `final` field, and calls `LocalDate.now(clock)` in the business operation. `Objects.requireNonNull()` rejects a missing clock source immediately when assembling the object.

When testing, each test case constructs the object with the appropriate clock. The `observedDate.isBefore(closingDate)` algorithm stays unchanged; only the source of “today” differs.

In production, the initialization site can supply the system clock with the business zone. Here is an illustrative example within a scope that can access the class above:

```java
RegistrationWindow production = new RegistrationWindow(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
```

Do not create `Clock.system(...)` inside `isOpenUntil()` if the design goal is to let the caller swap the time source. Nor is an `isTest` flag needed to branch to fixed data: the difference is expressed through the injected dependency.

Introducing `Clock` does not mean changing every method in the application. You can place the clock source only in the service layer that needs the “current” time, while other computation methods accept the already-read date or instant as ordinary data.

## 6. Changing the Zone Does Not Advance or Alter the Original Clock

`atBoundary.withZone(UTC)` returns a clock with the same instant but a different zone interpretation. The two clocks in the program produce different dates: UTC is still `2025-12-31`, while the Vietnam zone is already `2026-01-01`.

The `original view date` line is still `2026-01-01`, showing that `atBoundary`'s zone configuration was not modified. `same frozen instant = true` confirms that both still point to the exact same instant.

Thus, using `withZone()` to switch a clock's view is different from creating a fixed clock at a different instant. If you want to test the next day, you must choose another `Instant` corresponding to the target point in time, rather than arbitrarily changing the zone to force the date to change.

When choosing a point in time by local date-time, you can construct a `ZonedDateTime` with the zone and call `toInstant()` to pass into `Clock.fixed()`. In zones with daylight saving time transitions, an input local date-time may fall into a nonexistent gap or have two offsets; you must identify the exact instant to test rather than assuming a unique instant can be inferred from every `LocalDateTime`.

## 7. Fixed Means It Does Not Advance on Its Own

The final loop reads the clock multiple times and always receives the same `Instant`. Even if the program waits longer, a fixed clock does not drift or advance with real time. It also has no method to “reset” the instant like a mutable clock.

To test before and after an event, the simplest approach is to use separate fixed clocks such as `before` and `atBoundary`. This keeps each case independent and easy to read. When you genuinely need to simulate a sequence of instants within the same service object, choose an appropriate controllable time-source design; do not wait with `Thread.sleep()` expecting `Clock.fixed()` to advance.

Do not confuse `Clock.systemUTC()` with a fixed clock: it uses the running system clock with the UTC zone configured. `Clock.fixed()` keeps the instant frozen; the two options serve different needs.

## 8. Limitations to Remember When Writing Tests

**A clock only controls the code that uses it.** Database clocks, scheduled tasks, external services, or code calling `System.currentTimeMillis()` are not automatically replaced. A test spanning multiple components needs to know where timestamps are generated.

**A fixed clock does not trigger jobs.** Setting an instant that is “past due” only makes reads return that instant; it does not invoke a scheduler or wake waiting threads. Job execution behavior must be tested through the corresponding mechanism.

**Fixing time alone does not verify the business rule.** You must assert the business outcome, such as whether registration is open or closed. Merely checking that `clock.instant()` equals the passed-in instant is no substitute for testing the class that uses the clock.

**Scope the clock properly.** A fixed clock can be shared safely, but tests should not overwrite a global clock variable or let test instants leak into production configuration. Passing the time source through a dedicated object for the case under test keeps scenarios from interfering with one another.

Exercise: add a case one nanosecond after `midnight`. With the same closing date and Vietnam zone, the result must still be `false`. Then keep the same `midnight` instant but supply a UTC clock to a rule explicitly defined in terms of UTC dates: the observed date is still `2025-12-31`, so it has not yet reached the closing date `2026-01-01`. The two different outcomes are the consequence of two different zone contracts, not instability in `Clock.fixed()`.
