# Common Pitfalls Summary and Criteria for Choosing the Right API

## 1. Choosing an API Starts with the Question, Not the Method Name

Many date-time bugs do not come from syntax errors. The code still compiles and returns a valid date, yet it is answering a different question from what was required.

For example:

- “After one calendar day” can differ from “after exactly 24 hours”.
- “At the same instant” can differ from “having the same date-time and offset”.
- “The 31st of each month, clamping if shorter” differs from “taking the clamped day of the previous period and adding from there”.
- “Date-time 09:00” does not yet say where 09:00 is.
- “Valid until 10:00” needs to specify whether exactly 10:00 is still valid.

Before choosing an API, state four things: **what the data represents, what operation you want to perform, what the boundary policy is, and what information must be preserved during conversion**.

This article summarizes the criteria for choosing an API along with runnable counterexamples. The dates in the examples are fixed test data, not the current date.

## 2. First Criterion: Does the Data Type Have the Right Semantics?

| Question or data | Type to consider | Pitfall to avoid |
| --- | --- | --- |
| Calendar date, such as a birth date | `LocalDate` | Attaching a time or time zone that does not exist |
| Time of day, without a date | `LocalTime` | Expecting addition to retain next-day information |
| Local date-time pair | `LocalDateTime` | Calling it a unique instant when zone/offset is missing |
| Identified event instant | `Instant` | Storing as a local string that loses context |
| Date-time that must preserve its offset | `OffsetDateTime` | Keeping only the instant and assuming the original offset still exists |
| Date-time bound to zone rules | `ZonedDateTime` or a model with an explicit `ZoneId` | Replacing the zone with a fixed offset for all dates |
| A monthly period | `YearMonth` | Using a standalone month and losing the year |
| A year | `Year` | Creating a fake Jan 1 date if the domain has no such date |
| Recurring month-day pattern | `MonthDay` | Using it instead of a full birth date when age calculation is needed |

A type with more fields is not necessarily better. Using `LocalDateTime` for all data can both add information that has no source and still lack instant information.

`Instant` identifies a point on the timeline, but does not store the zone name where the event was recorded. `LocalDate` holds the date, but does not hold the time zone that was used to derive that date. Choose and preserve the right information for the purpose; see [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) and [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 3. Second Criterion: Setting a Component or Adding an Amount?

| Intent | Typical API |
| --- | --- |
| Read a component | `getYear()`, `get(DAY_OF_MONTH)`, `getLong(field)` |
| Set a field to a value | `withDayOfMonth(1)`, `with(field, value)` |
| Apply an adjustment rule | `with(lastDayOfMonth())` |
| Add an amount by a unit | `plusDays(1)`, `plus(1, DAYS)` |
| Add a packaged amount | `plus(Period)`, `plus(Duration)` |
| Measure the amount between two values | `ChronoUnit.X.between(start, end)` |

`with(DAY_OF_MONTH, 1)` sets the date to the 1st of the month. `plus(1, DAYS)` advances by one day. Do not choose between them just because both take the number 1.

`ChronoField` describes a field; `ChronoUnit` describes a unit. `DAY_OF_MONTH` does not substitute for `DAYS`. When an API accepts the general `Temporal` interface, it still does not give the object extra components: `LocalDate` cannot add `HOURS`.

Only use `get` when the contract allows an `int` value. Some fields with a large range, such as `NANO_OF_DAY`, must be read via `getLong`. Switching from `get` to `getLong` does not make an unsupported field supported.

With standard immutable types, always keep the returned result when you need to use the change:

```java
// Illustrated inside a method.
LocalDate date = LocalDate.of(2024, 1, 31);
date.plusDays(1);          // Result discarded; date is still Jan 31.
date = date.plusDays(1);   // date is now Feb 1.
```

Reassigning the variable does not mutate the original object. When comparing values, use `equals` or a semantic comparison, not `==`.

## 4. Third Criterion: Calendar Rules or Elapsed Duration?

`Period` describes a calendar-based year-month-day amount. `Duration` describes an amount in seconds and nanoseconds. On a zoned type, this difference becomes apparent when the offset changes.

For example, in Paris, starting from 12:00 on 30/3/2024:

| Addition | Resulting local time |
| --- | --- |
| `plus(Period.ofDays(1))` | 12:00 on 31/3 |
| `plus(Duration.ofHours(24))` | 13:00 on 31/3 |

The next calendar day keeps the local time of day in the example, but the actual elapsed time is only 23 hours. Do not turn the requirement “every day at 12:00” into “every 24 hours” without evaluating the consequences.

Similarly:

- A month does not have a fixed number of days.
- A year does not always have 365 days.
- The result of `ChronoUnit.MONTHS.between` is the number of complete months according to the data type's rules, not necessarily the inverse of adding months with clamping.
- Date intervals and instant intervals must be measured with the appropriate question.

When converting a local date-time to an instant, an hour during an offset transition may not exist or may exist twice. `ZonedDateTime` has default handling rules, but business logic may need to reject it or require choosing an offset. Do not treat “attaching a zone succeeded” as proof that the original input always has a single unambiguous interpretation. See the gap/overlap cases in [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).

## 5. Fourth Criterion: Policy at Month-End and Leap Days

### 5.1. Adding Months Can Lose the Original Day Number

Starting from 31/1/2024:

```text
Add 1 month, then add 1 month:  29/3/2024
Add 2 months directly:          31/3/2024
```

Stepping through February clamped day 31 down to 29. When continuing from the clamped value, the original day number is no longer in the object.

If the requirement is “the last day of each month”, use each month's `YearMonth` period and call `atEndOfMonth()`. If the requirement is “the 30th, clamping if shorter”, keep the requested day number 30 separately and apply it to each month. The two policies are not automatically synonymous.

Likewise, do not use adding and then subtracting months as a guaranteed undo operation to restore the original day. Clamped information may not come back on its own.

### 5.2. Leap Days Are Not Just Divisibility by 4

Key cases:

- 1900 is not a leap year.
- 2000 is a leap year.
- 2100 is not a leap year.
- 2024 is a leap year.

Use the calendar API to determine leap years and construct valid dates, and test century cases to verify the rules properly.

### 5.3. Constructing a Valid Date Differs from Rejecting Invalid Input

`MonthDay.of(2, 29).atYear(2023)` yields 28/2/2023. That is the adjustment behavior of the API.

If the requirement is to validate “does 29/2/2023 exist?”, do not use that result to conclude the input is valid. Check `Year.isValidMonthDay` or construct the date through the corresponding strict path.

Completed years of age and Feb 29 anniversaries also require a policy: in a common year, do you choose Feb 28, Mar 1, or no occurrence? The API does not automatically know your application's rule. Taking `Period.getYears()` and calling it the age may not satisfy every chosen policy.

## 6. Fifth Criterion: What Must “Equality” Preserve?

Consider two values:

```text
2024-01-15T09:00+07:00
2024-01-15T02:00Z
```

They represent the same instant, but have different date-time and offset pairs.

| Requirement | Appropriate comparison |
| --- | --- |
| Same calendar date | `LocalDate.equals` |
| Same local date-time | `LocalDateTime.equals` |
| Same instant | Compare `Instant`, or `OffsetDateTime.isEqual` |
| Same date-time and offset | `OffsetDateTime.equals` |
| Need to preserve zone name | Check value and `ZoneId` according to contract |

Do not compare formatted strings as a substitute for all comparisons. A display pattern may omit seconds, fractional seconds, offset, or zone. Two different values can have the same screen label.

When sorting, choose the same criterion as the requirement: if you need global event order, compare instants; if you need to sort calendar dates, compare `LocalDate`. Do not let the lexicographical order of strings decide.

## 7. Sixth Criterion: The Source of “Now” and Business Dates

`LocalDate.now()` uses the JVM default time zone. A UTC server and a user in Vietnam can be on two different calendar dates at the same instant.

If the requirement is today according to a business zone:

1. Determine the source of the instant using `Clock`.
2. Choose `ZoneId` according to business rules.
3. Derive the date using `LocalDate.ofInstant(reference, zone)` or a clock already bound to the right zone.

At `2024-01-01T17:00Z`, the UTC date is still Jan 1, whereas the date in Vietnam is Jan 2 in the example.

Use a single reference instant per processing pass to avoid multiple calls crossing midnight. In tests, use `Clock.fixed`; do not wait with sleep and do not use the test machine's current date as the expected result.

Changing a clock's zone does not shift the underlying instant. Adding 7 hours to an instant is not the right way to represent viewing the same instant in another zone. See how to swap the time source in [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).

## 8. Seventh Criterion: Formatting, Validation, and Interchange

A data flow should have clear boundaries:

```text
External data
   ↓ parse according to contract
Java date-time type
   ↓ validate and compute
Typed result
   ↓ format for user/protocol
Output string
```

Common pitfalls at the boundaries:

| Pitfall | Correct choice |
| --- | --- |
| Parsing dates while leaving default auto-adjustment enabled | Choose `ResolverStyle.STRICT` if invalid dates must be rejected |
| Confusing `MM` with `mm` | `MM` is month; `mm` is minute |
| Confusing `uuuu`, `yyyy`, `YYYY` | Distinguish proleptic year, year-of-era, and week-based-year |
| Parsing local time into `Instant` without an offset | Require an explicit offset or zone rule |
| Using an undocumented default locale/time zone | Pass them explicitly according to contract |
| Formatting and then splitting strings to compute | Keep the typed object and use field/calculation APIs |
| Catching an error and substituting the current date | Report the error or handle missing data per policy |

`DateTimeFormatter` is immutable and thread-safe by contract; it can be explicitly configured with locale, zone, and resolver style. Migrating to the modern API does not mean just renaming classes while keeping ambiguous string usage. See [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 9. Eighth Criterion: Units, Precision, and Storage

An epoch number is only meaningful when its unit is known: seconds and milliseconds cannot be mixed up. `Instant` separates epoch seconds and nanoseconds; going through `toEpochMilli` loses sub-millisecond precision.

For example:

```text
Original:  2024-01-15T02:00:00.123456789Z
Via milli: 2024-01-15T02:00:00.123Z
```

With JDBC or external systems, you must determine:

- Whether the column/data carries an instant or a local date-time.
- At which step the time zone is applied.
- The precision level and rounding/truncation rule.
- How missing values are represented.
- Which types the driver/mapper supports.

`Timestamp.toInstant` and `Timestamp.toLocalDateTime` serve different purposes; choose based on data semantics and check the JDBC contract. A conversion method cannot fix time zone information that was already misinterpreted during the read step.

Round-trip tests must compare according to what must be preserved. If the store only keeps microseconds and the policy allows truncation, compare against the value normalized according to that rule. Do not use a wide tolerance threshold to hide bugs.

## 10. Ninth Criterion: Are Time Bounds Inclusive or Exclusive?

For a half-open validity interval:

```text
[fromInclusive, untilExclusive)
```

The condition is:

```text
from <= reference AND reference < until
```

Exactly at the start bound, it is active; exactly at the end bound, it is no longer active. Two adjacent intervals can share a boundary without double-counting.

If the UI selects “through the end of May 31”, the exclusive end instant should be the start of June 1 in the business zone. Do not guess the end of day using 23:59:59 or subtract an arbitrary small unit.

Boundary rules must be consistent across Java, database queries, and the UI. A variable name like `untilExclusive` is more helpful than an `end` variable whose meaning is unclear.

## 11. Java 17+ Program to Verify Common Pitfalls

Save the following code as `ChooseDateTimeApi.java`. The program is standalone, requires no external libraries, and does not read the system clock.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.MonthDay;
import java.time.OffsetDateTime;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Locale;
import java.util.Objects;

public class ChooseDateTimeApi {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    private static boolean active(Instant value, Instant from, Instant until) {
        if (!from.isBefore(until)) {
            throw new IllegalArgumentException("Invalid interval");
        }
        return !value.isBefore(from) && value.isBefore(until);
    }

    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        eq(LocalDate.parse("2024-02-29", strict), LocalDate.of(2024, 2, 29));
        rejects(DateTimeParseException.class,
                () -> LocalDate.parse("2023-02-29", strict));
        rejects(DateTimeParseException.class,
                () -> Instant.parse("2024-01-15T09:00:00"));

        LocalDate date = LocalDate.of(2024, 1, 31);
        date.plusDays(1); // Discarding the returned value changes nothing.
        eq(date, LocalDate.of(2024, 1, 31));
        eq(date.with(ChronoField.DAY_OF_MONTH, 1), LocalDate.of(2024, 1, 1));
        eq(date.plus(1, ChronoUnit.DAYS), LocalDate.of(2024, 2, 1));
        eq(date.plusMonths(1), LocalDate.of(2024, 2, 29));
        eq(date.plusMonths(1).plusMonths(1), LocalDate.of(2024, 3, 29));
        eq(date.plusMonths(2), LocalDate.of(2024, 3, 31));
        eq(YearMonth.from(date).plusMonths(2).atEndOfMonth(),
                LocalDate.of(2024, 3, 31));
        eq(Year.isLeap(1900), false);
        eq(Year.isLeap(2000), true);
        MonthDay leapDay = MonthDay.of(2, 29);
        eq(leapDay.atYear(2023), LocalDate.of(2023, 2, 28));
        eq(Year.of(2023).isValidMonthDay(leapDay), false);

        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime noon = ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);
        ZonedDateTime calendarDay = noon.plus(Period.ofDays(1));
        ZonedDateTime elapsedDay = noon.plus(Duration.ofHours(24));
        eq(calendarDay.getHour(), 12);
        eq(elapsedDay.getHour(), 13);
        eq(Duration.between(noon.toInstant(), calendarDay.toInstant()).toHours(), 23L);

        Clock fixed = Clock.fixed(Instant.parse("2024-01-01T17:00:00Z"),
                ZoneOffset.UTC);
        eq(LocalDate.now(fixed), LocalDate.of(2024, 1, 1));
        eq(LocalDate.ofInstant(fixed.instant(), ZoneId.of("Asia/Ho_Chi_Minh")),
                LocalDate.of(2024, 1, 2));

        OffsetDateTime localOffset = OffsetDateTime.parse("2024-01-15T09:00+07:00");
        OffsetDateTime utcOffset = OffsetDateTime.parse("2024-01-15T02:00Z");
        eq(localOffset.isEqual(utcOffset), true);
        eq(localOffset.equals(utcOffset), false);
        LocalDateTime ambiguous = LocalDateTime.parse("2024-10-27T02:30");
        eq(paris.getRules().getValidOffsets(ambiguous).size(), 2);

        Instant precise = Instant.parse("2024-01-15T02:00:00.123456789Z");
        eq(Instant.parse(precise.toString()), precise);
        eq(Instant.ofEpochMilli(precise.toEpochMilli()).equals(precise), false);
        Instant from = precise;
        Instant until = from.plusSeconds(60);
        eq(active(from, from, until), true);
        eq(active(until, from, until), false);
        rejects(UnsupportedTemporalTypeException.class,
                () -> date.plus(1, ChronoUnit.HOURS));

        System.out.println("calendarDayHour=" + calendarDay.getHour());
        System.out.println("elapsed24HoursHour=" + elapsedDay.getHour());
        System.out.println("calendarDayElapsedHours="
                + Duration.between(noon.toInstant(), calendarDay.toInstant()).toHours());
        System.out.println("sameInstant=" + localOffset.isEqual(utcOffset));
        System.out.println("sameOffsetDateTime=" + localOffset.equals(utcOffset));
        System.out.println("businessDate=" + LocalDate.ofInstant(
                fixed.instant(), ZoneId.of("Asia/Ho_Chi_Minh")));
        System.out.println("activeAtEnd=" + active(until, from, until));
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ChooseDateTimeApi.java
java ChooseDateTimeApi
```

Stdout:

```text
calendarDayHour=12
elapsed24HoursHour=13
calendarDayElapsedHours=23
sameInstant=true
sameOffsetDateTime=false
businessDate=2024-01-02
activeAtEnd=false
PASS checks=27
```

The `eq` helper actively throws `AssertionError` on mismatch, so the `-ea` flag is not needed. The `rejects` helper verifies the exact exception type rather than treating any arbitrary error as a pass.

The first few lines clarify that one calendar day differs from exactly 24 hours. The two offset comparison lines show that the equality criterion must be chosen deliberately. The business date is derived from a fixed instant. The `activeAtEnd=false` line confirms the exclusive end bound.

The remaining checks also verify strict parsing, discarding immutable return values, setting a field versus adding an amount, day drift when adding months, century leap-year rules, repeated local hours, precision loss, and unsupported units.

You can run two configurations to detect hidden dependencies:

```shell
java "-Duser.timezone=UTC" ChooseDateTimeApi
java "-Duser.timezone=America/New_York" ChooseDateTimeApi
```

Both must produce the exact same stdout as above. The example uses fixed dates based on the JDK's zone rules; it does not prove behavior for an untested driver or database.

## 12. Process for Choosing an API for a New Requirement

Follow these steps in order:

1. **Rewrite the requirement with concrete data.** For example, “expires at the start of the day after May 31 in the base zone,” instead of simply writing “expires at month-end.”
2. **Choose the type that preserves the right information.** Separate calendar dates, instants, local times, and recurring patterns.
3. **Choose the operation.** Set a field, adjust by a rule, add calendar units, add elapsed duration, or measure an interval.
4. **Declare boundary policies.** Leap days, short months, missing/ambiguous hours, and inclusive/exclusive bounds.
5. **Identify the environment.** Clock, zone, and locale must have explicit sources whenever they affect the result.
6. **Define what information must be preserved on conversion.** Instant, offset, zone, and precision are distinct criteria.
7. **Write test cases that distinguish the right choice from plausible-looking wrong ones.** Pick month-end, century years, midnight, or offset transitions.
8. **Only claim what has been verified.** In-memory tests do not replace real storage read/write tests.

A simple function does not have to handle every calendar system and every zone automatically. A narrow, explicit contract can be better than a generic function that accepts anything and guesses the intent.

## 13. Self-Check Exercises

1. **“Daily reminder at 09:00 in Paris” vs. “reminder every 24 hours”?** Choose two separate models and predict the difference on an offset-transition day.

2. **“Last day of each month starting from Jan 2024”.** The first three periods must be 31/1, 29/2, and 31/3. Explain why chaining month additions from the clamped date may fail this requirement.

3. **“Two time strings with different offsets but the same instant”.** State when to use `isEqual` and when `equals` is needed; do not choose just because a comparison returns `true`.

4. **“The user enters 29/2/2023 and the system must reject it”.** Choose a strict parsing/construction path. Do not treat an auto-adjusted 28/2 result as proof that the data is valid.

5. **“The store only saves milliseconds, but the input has nanoseconds”.** Determine whether precision loss is acceptable, what the rule is, and what value to compare against in round-trip checks.

6. **“An event at exactly 10:00 at the boundary of two intervals”.** Given `[09:00,10:00)` and `[10:00,11:00)`, the event belongs to the second interval.

A right API choice must match the data semantics and stated policies. Boundary cases help prove that alignment, rather than merely proving that the method can run.
