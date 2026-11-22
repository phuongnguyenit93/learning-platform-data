# Testing Month-End, Leap Years, Midnight, and DST Transitions

## Time Bugs Often Appear at Boundaries

A function that retrieves today's date might work correctly all afternoon but fail near midnight if it uses the wrong time zone. A recurring schedule on the 31st might work in January but break in February. An appointment at 02:30 might not exist or might occur twice on a daylight saving time (DST) transition day.

Effective time testing requires **proactively setting inputs at boundaries**, rather than waiting for the actual calendar date. In Java, `Clock.fixed` helps control "now"; fixed date-time values help test calendar calculations and time-zone rules.

This article uses ISO calendar dates and the `Europe/Paris` DST examples in 2024. The goal is to verify the rules chosen by the application, without assuming every product must choose the same way to handle non-existent dates or repeated hours.

## 1. Write Expected Rules Before Writing Test Cases

A test is only valuable when you know which result is correct.

Examples of the rules illustrated in this article:

| Scenario | Chosen Rule |
| --- | --- |
| Selecting day 31 in a month without 31 days | Use the last valid day of that month |
| Service's "today" | Calculated according to the zone of the passed-in Clock |
| Current instant equals the deadline | Expired; the end bound is exclusive |
| Local time falls into a skipped DST gap | If preserving the exact time/offset is required, reject the invalid combination |
| Repeated hour due to DST | The provided offset distinguishes the two occurrences |

A different rule can also be valid, such as skipping months that do not have a 31st day. If the business logic chooses that, the test cases must reflect that rule rather than copying the results from this article.

It is also necessary to distinguish **API behavior** from **application policy**. `atZone` has a default way of handling non-existent hours, but the application may require rejecting them instead of automatically shifting the time.

## 2. Boundary Case Matrix to Include

| Category | Cases to Proactively Select |
| --- | --- |
| Month-end | Months with 28, 29, 30, 31 days; rolling over from December to the next year if the calculation has that step |
| Leap year | Common year; year divisible by 4; non-leap century year; leap year divisible by 400 |
| Midnight | Just before, at, and just after midnight in the business time zone |
| DST spring forward | Before the skipped gap, inside the non-existent gap, after the gap |
| DST fall back | Both valid offsets of the same local time; compare `Instant` as well |
| Boundary instants | Before deadline, at deadline, after deadline |

It is not necessary to combine every case with every other case into a huge Cartesian product. Choose the cases that can expose false assumptions in the logic under test.

A mid-month date or a midday timestamp can serve as a control case, but it does not replace the boundaries above.

## 3. Controlling "Now" with an Injected Clock

Business code that depends directly on `LocalDate.now()` will read the environment's default time and zone. Instead, accept a Clock and read:

```java
LocalDate today = LocalDate.now(clock);
```

In tests:

```java
Clock clock = Clock.fixed(
        Instant.parse("2024-06-30T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

These are illustrative snippets; you need to import the corresponding classes in `java.time`.

This 17:00Z instant is exactly 00:00 on 01/07 in the Vietnam time zone used in the example. Setting the Clock to UTC will not test the same question of "today in Vietnam".

A fixed Clock always returns the chosen instant. There is no need to `sleep`, change the machine clock, or run tests on the actual last day of the month. [`Clock.fixed` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId))

## 4. Complete Test Program Without External Libraries

Save as `TimeBoundaryChecks.java`. The program runs on Java 17 or later. If a condition is false, it throws `AssertionError`; the checks do not depend on the flag enabling/disabling the `assert` keyword.

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Objects;

public class TimeBoundaryChecks {
    private static int checks;

    private static void expect(
            String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void expectDateTimeFailure(
            String label, Runnable action) {
        try {
            action.run();
        } catch (DateTimeException ex) {
            checks++;
            return;
        }
        throw new AssertionError(label + ": expected DateTimeException");
    }

    // Application rule: requested day 1..31;
    // if the month is shorter, use the last day of the month.
    static LocalDate scheduledDate(YearMonth month, int requestedDay) {
        if (requestedDay < 1 || requestedDay > 31) {
            throw new IllegalArgumentException("Ngay mong muon phai trong 1..31");
        }
        return month.atDay(Math.min(requestedDay, month.lengthOfMonth()));
    }

    static LocalDate businessToday(Clock clock) {
        return LocalDate.now(clock);
    }

    static boolean isExpired(Clock clock, Instant endExclusive) {
        return !clock.instant().isBefore(endExclusive);
    }

    public static void main(String[] args) {
        expect("normal February", LocalDate.of(2023, 2, 28),
                YearMonth.of(2023, 2).atEndOfMonth());
        expect("leap February", LocalDate.of(2024, 2, 29),
                YearMonth.of(2024, 2).atEndOfMonth());
        expect("April", LocalDate.of(2024, 4, 30),
                YearMonth.of(2024, 4).atEndOfMonth());
        expect("requested 31 in February", LocalDate.of(2024, 2, 29),
                scheduledDate(YearMonth.of(2024, 2), 31));
        expect("requested 31 in March", LocalDate.of(2024, 3, 31),
                scheduledDate(YearMonth.of(2024, 3), 31));
        System.out.println("monthChecks=PASS");

        expect("1900", false, Year.isLeap(1900));
        expect("2000", true, Year.isLeap(2000));
        expect("2100", false, Year.isLeap(2100));
        expect("leap day plus year", LocalDate.of(2025, 2, 28),
                LocalDate.of(2024, 2, 29).plusYears(1));
        System.out.println("leapYearChecks=PASS");

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant midnight = Instant.parse("2024-06-30T17:00:00Z");

        Clock before = Clock.fixed(midnight.minusNanos(1), vietnam);
        Clock at = Clock.fixed(midnight, vietnam);
        Clock after = Clock.fixed(midnight.plusNanos(1), vietnam);

        expect("before midnight", LocalDate.of(2024, 6, 30),
                businessToday(before));
        expect("at midnight", LocalDate.of(2024, 7, 1),
                businessToday(at));
        expect("after midnight", LocalDate.of(2024, 7, 1),
                businessToday(after));
        expect("same instant in UTC", LocalDate.of(2024, 6, 30),
                businessToday(at.withZone(ZoneOffset.UTC)));

        expect("before expiry", false, isExpired(before, midnight));
        expect("at expiry", true, isExpired(at, midnight));
        expect("after expiry", true, isExpired(after, midnight));
        System.out.println("midnightChecks=PASS");

        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);

        expect("gap has no valid offset", 0,
                paris.getRules().getValidOffsets(gap).size());
        expect("default gap adjustment", LocalDateTime.of(2024, 3, 31, 3, 30),
                gap.atZone(paris).toLocalDateTime());
        expectDateTimeFailure("strict gap rejection",
                () -> ZonedDateTime.ofStrict(
                        gap, ZoneOffset.ofHours(1), paris));

        LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);
        expect("overlap has two offsets", 2,
                paris.getRules().getValidOffsets(overlap).size());

        ZonedDateTime first = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.ofHours(2), paris);
        ZonedDateTime second = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.ofHours(1), paris);

        expect("first overlap instant", Instant.parse("2024-10-27T00:30:00Z"),
                first.toInstant());
        expect("second overlap instant", Instant.parse("2024-10-27T01:30:00Z"),
                second.toInstant());
        expect("overlap minutes apart", 60L,
                Duration.between(first.toInstant(), second.toInstant()).toMinutes());

        ZonedDateTime noonBefore =
                LocalDateTime.of(2024, 3, 30, 12, 0).atZone(paris);
        expect("one calendar day elapsed hours", 23L,
                Duration.between(
                        noonBefore.toInstant(),
                        noonBefore.plusDays(1).toInstant()).toHours());
        expect("24 hours gives local 13", 13,
                noonBefore.plus(Duration.ofHours(24)).getHour());

        System.out.println("dstChecks=PASS");
        System.out.println("totalChecks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 TimeBoundaryChecks.java
java TimeBoundaryChecks
```

Stdout when all checks pass, with the 2024 Paris rules as in the example:

```text
monthChecks=PASS
leapYearChecks=PASS
midnightChecks=PASS
dstChecks=PASS
totalChecks=25
```

In a project with JUnit, you can convert the groups into test methods and use the corresponding assertions. Test names should state the rule/boundary being tested, not just a number.

## 5. Month-End: Test the Policy, Not Just Calling the API

The `scheduledDate` function keeps the **requested day** separate from the resulting date. For a request of day 31:

```text
month 02/2024 → execution date 29/02
month 03/2024 → execution date 31/03
```

If you instead take February's result and add one month, day 29 could carry over into March, losing the intent of day 31.

A test that only verifies "February returns a valid date" will not catch this recurring schedule bug. You need to add a case for the following month restoring the intended day.

`YearMonth.atEndOfMonth()` computes the end of the month for a specific year and month. [`YearMonth` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/YearMonth.html#atEndOfMonth())

For `LocalDate` month/year addition, the day may be adjusted to the last valid day of the target month. For example, the program checks that 29/02/2024 plus one year becomes 28/02/2025. This API behavior does not by itself decide the application's entire anniversary-date policy. [Year addition documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#plusYears(long))

If the business logic wants 01/03 when 29/02 does not exist, that rule must be written separately and verified against the exact expectation.

## 6. Leap Years: Use Cases That Break Naive Formulas

The cases 1900, 2000, and 2100 are valuable because a check that only tests "divisible by 4" will return the wrong result for non-leap century years.

There is no need to reimplement the leap-year algorithm if the library already provides it. In application logic, what needs verification is that outputs such as due dates, recurring schedules, or report ranges use the correct target year.

For example, a test dataset might include:

| Input | Expected Calendar Result |
| --- | --- |
| 28/02/2023 plus one day | 01/03/2023 |
| 28/02/2024 plus one day | 29/02/2024 |
| 29/02/2024 plus one day | 01/03/2024 |
| End of month 02/1900 | 28/02/1900 |
| End of month 02/2000 | 29/02/2000 |

Expected results are stated explicitly as calendar facts, rather than computing the expected value in the test using the very formula under test.

## 7. Midnight: Set the Timestamp in the Business Zone

The program places three Clocks around:

```text
2024-07-01 00:00 Asia/Ho_Chi_Minh
= 2024-06-30 17:00Z
```

If `businessToday` ignores the passed-in Clock and fetches the date in UTC, the cases at and after midnight will detect the discrepancy.

The three before–at–after cases also test the expiration boundary:

```text
now < endExclusive  → not expired yet
now = endExclusive  → expired
now > endExclusive  → expired
```

The nanosecond offset in the example shows how close the test data is to the boundary, not a guarantee that the system clock or database has nanosecond precision.

If the storage layer only keeps milliseconds, integration tests are needed for rounding/truncation at that layer. Do not infer from in-memory `Instant` tests that all data layers preserve the same precision.

In addition, if an operation produces multiple values that must be consistent, capture a single instant and derive the dates/times from that same instant. Two independent reads from a live clock can land on opposite sides of midnight.

## 8. DST Spring Forward: A Local Time May Not Exist

In Paris on 31/03/2024, `02:30` falls into the skipped hour gap. `getValidOffsets` returns an empty list.

The program tests two intentional behaviors simultaneously:

- `gap.atZone(paris)` applies the default policy and adjusts it to `03:30`.
- `ZonedDateTime.ofStrict` rejects the invalid local-time/offset combination.

The two outcomes do not contradict each other in correctness; they are two different contracts. A scheduling application needs to choose whether to accept automatic time adjustment or ask the user to pick another time.

When testing scheduling inputs, do not just assert that the call does not throw an exception. If automatic adjustment is allowed, assert the adjusted local time, offset, and `Instant`. If it is not allowed, assert the exact rejection type. [`ZonedDateTime` gap-handling documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

## 9. DST Fall Back: A Local Time May Refer to Two Instants

In Paris on 27/10/2024, `02:30` has two valid offsets:

```text
02:30 +02:00 → 00:30Z
02:30 +01:00 → 01:30Z
```

If you only compare `LocalDateTime`, the two occurrences look equal. Comparing `Instant` shows they are one hour apart.

A DST fall-back test case needs to know which occurrence is selected. You can require the user to provide the offset or apply a documented earlier/later occurrence policy. Do not omit the offset from the expected result and treat both outcomes as equivalent.

`ZoneRules.getValidOffsets(localDateTime)` helps identify the three states: no offset, one offset, or two offsets. [`getValidOffsets` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

Daylight saving time does not occur in every zone, and the shift should not be assumed to always be one hour across all historical rules. The one-hour Paris case is concrete data, not an algorithm replacing the time-zone database.

## 10. A Calendar Day Differs from a 24-Hour Duration

From 12:00 on 30/03/2024 in Paris:

- `plusDays(1)` finds the next calendar day with the corresponding local time; in the example only 23 hours elapse.
- `plus(Duration.ofHours(24))` adds an exact 24-hour duration; the resulting local time is 13:00 the next day.

If a class schedule requires "every day at 12:00", the test needs to check the local time across the DST transition. If it requires "after 24 hours", it needs to check the duration between the two `Instant` values.

Do not check only the target date, because both can fall on the same date but at different times. Similarly, at a DST fall-back transition, one calendar day can correspond to 25 hours in a one-hour shift.

Tests should make clear which quantity the business logic preserves: wall-clock time, calendar day, or elapsed duration.

## 11. Keeping the Test Suite Stable and Useful

- Pass a Clock or timestamp wherever "now" is needed; avoid hidden default calls inside logic.
- Use fixed date-times and explicit zones.
- Do not mutate the JVM's global time zone to test a function if you can pass the zone/Clock directly.
- Do not use real-time waiting as a way to test schedules or expiration.
- Record the JDK/time-zone data version when investigating a DST case that differs from expected.
- For future rules, understand that zone data can be updated; distinguish environment changes from algorithm bugs.
- When moving to project tests, test the actual business classes, not just repeat library API examples.

You can add properties for appropriate algorithms, such as the selected day never exceeding the target month or repeatedly taking the end of the month yielding the same value. However, do not impose false properties like "adding one month then subtracting one month always returns the original date"; month-end adjustment can lose the original day.

## 12. Self-Practice

1. Why is testing only the 15th of each month insufficient for a schedule on the 31st?
2. Why can a fixed Clock with the right UTC instant but the wrong zone still make a "today" test meaningless?
3. What needs to be checked besides `LocalDateTime` when a time occurs twice due to DST?
4. Is `plusDays(1)` always equal to adding 24 actual hours?
5. If being exactly at the expiration instant already counts as expired, is `isAfter` sufficient?

Suggested answers:

1. Because it never hits months with fewer days and misses losing the requested day in subsequent periods.
2. Local date depends on both the instant and the zone.
3. Check the offset and `Instant` of the chosen occurrence.
4. No; an offset transition can make the elapsed duration different.
5. No; you need to include the exact-boundary case, such as `!now.isBefore(endExclusive)`.

Push time to its boundaries with test data, clearly define what is preserved, and verify both the date-time values and the business meaning of the result.
