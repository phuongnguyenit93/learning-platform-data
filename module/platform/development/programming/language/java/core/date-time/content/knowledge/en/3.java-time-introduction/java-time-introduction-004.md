# Immutable Modifications with with...(), plus...(), and minus...() in java.time

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why Java's modern date-time objects are **immutable** and why calls to `with...()`, `plus...()`, and `minus...()` do not modify the original object.
- Distinguish between **setting/replacing a date-time component** and **shifting by a period/amount of time**, and choose the right method for your business requirement.
- Use overloads such as `with(TemporalField, long)`, `with(TemporalAdjuster)`, `plus(long, TemporalUnit)`, and `minus(long, TemporalUnit)`.
- Accurately understand end-of-month adjustments, leap years, field limits, method chaining, time zones, and daylight saving time (DST).
- Avoid losing results by forgetting to capture return values, using the wrong class/unit, or assuming that adding one calendar day always equals 24 elapsed hours.

The context is the `java.time` APIs in Java 17 and later. The lesson uses examples with fixed dates so that the output can be verified deterministically.

## 2. What Does Immutability Mean?

Common value classes such as `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `ZonedDateTime`, `OffsetDateTime`, `Duration`, and `Period` are designed to be immutable: once created, a date-time value cannot be modified in place. A "modification" method **returns a resulting value** for you to use further.

```java
LocalDate original = LocalDate.of(2024, 1, 31);
original.plusDays(1);                    // result is discarded
System.out.println(original);            // 2024-01-31

LocalDate nextDay = original.plusDays(1);
System.out.println(nextDay);             // 2024-02-01
System.out.println(original);            // 2024-01-31
```

This is an **illustrative snippet** inside a method, requiring `import java.time.LocalDate;`. Calling `original.plusDays(1)` is not an assignment; if you discard the return value, the variable `original` still references the old value.

There are three common usage patterns:

```java
LocalDate revised = original.plusDays(7); // keep both the old and new values
original = original.plusDays(7);           // reassign variable to the new value
LocalDate result = original.withDayOfMonth(1).plusMonths(1).minusDays(2);
```

- **Object immutability** is different from **variable reassignability**: the statement `original = ...` changes which value the variable references; it does not mutate the object that was already created.
- Methods may return the **same instance** if the result does not change; your contract should rely on **value equality**, not on the assumption that "every call creates a new object."
- Compare values using `equals()` or appropriate temporal comparison methods, and avoid using `==` to check whether two dates have the same value.
- Immutable values are safe to share across threads for reading; if multiple threads reassign/update a shared reference variable, coordination is still required for atomic updates.

## 3. Distinguishing the Three Method Families

| API Family | Core Meaning | Example | Result from `2024-01-31` |
| --- | --- | --- | --- |
| `with...()` | **Set/replace** a field or apply an adjustment rule | `withDayOfMonth(1)` | `2024-01-01` |
| `plus...()` | **Add** an amount or a unit | `plusDays(1)` | `2024-02-01` |
| `minus...()` | **Subtract** an amount or a unit | `minusDays(1)` | `2024-01-30` |

For example, `withMonth(6)` means choosing **month 6 (June)**, whereas `plusMonths(6)` means **moving forward 6 months**. Similarly, `withHour(9)` sets the hour to 09; `plusHours(9)` adds 9 hours. These methods are not present on every class, because a `LocalDate` has no hour field and a `LocalTime` has no year field.

You should phrase the requirement clearly before choosing an API:

- "Change the payment due date to the **1st day** of the current month" → set the field with `withDayOfMonth(1)`.
- "Extend by **one calendar month**" → add with `plusMonths(1)`.
- "Move the appointment back **three days**" → subtract with `minusDays(3)`.
- "Select the **next Monday**" → use the rule `TemporalAdjusters.next(DayOfWeek.MONDAY)`.

## 4. The with...() Family: Replacing Fields or Applying Rules

### 4.1. Field-Named Methods

```java
LocalDate date = LocalDate.of(2024, 8, 23);
LocalDate firstDay = date.withDayOfMonth(1); // 2024-08-01
LocalDate otherYear = date.withYear(2025);   // 2025-08-23

LocalDateTime time = LocalDateTime.of(2024, 8, 23, 9, 45);
LocalDateTime revised = time.withHour(14).withMinute(0);
// 2024-08-23T14:00
```

This snippet requires `import java.time.LocalDate;` and `import java.time.LocalDateTime;` and is placed inside a method. `withYear(2025)` selects the year 2025; `withDayOfMonth(1)` selects day 1 of the month. Neither adds to the current value.

Common operations include:

- `LocalDate.withYear(...)`, `withMonth(...)`, `withDayOfMonth(...)`, `withDayOfYear(...)`.
- `LocalTime.withHour(...)`, `withMinute(...)`, `withSecond(...)`, `withNano(...)`.
- `LocalDateTime` combines both date and time fields.
- `ZonedDateTime` and `OffsetDateTime` also provide zone/offset-related operations, though you need to understand how they handle local date-time values and instants.

**Note:** Not every input value is valid. For example, `LocalDate.of(2024, 2, 29).withDayOfMonth(30)` throws `DateTimeException`. However, some other field replacements are defined to **adjust to the last valid day of the month**: `LocalDate.of(2024, 1, 31).withMonth(2)` produces `2024-02-29`. Do not assume every `with...()` method follows the same policy when the target date is invalid; check the rules of the specific method.

### 4.2. The General Form with(field, value)

Classes implementing `Temporal` may also support `with(TemporalField field, long newValue)`. For example, using `ChronoField`:

```java
import java.time.LocalDate;
import java.time.temporal.ChronoField;

public class WithFieldDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 8, 23);
        LocalDate edited = date.with(ChronoField.DAY_OF_MONTH, 5);
        System.out.println(edited); // 2024-08-05
    }
}
```

Save this as `WithFieldDemo.java`, compile with `javac WithFieldDemo.java`, and run `java WithFieldDemo`. The output displays `2024-08-05`. This form is useful when the field is chosen dynamically, though it is less readable than `withDayOfMonth(5)` in straightforward business code.

**Not every field is supported by every temporal object.** For example, `LocalDate` does not support `ChronoField.HOUR_OF_DAY`. You can check beforehand with `date.isSupported(ChronoField.HOUR_OF_DAY)` (which returns `false`); calling `with(...)` with an unsupported field throws `UnsupportedTemporalTypeException`.

### 4.3. with(adjuster): Adjusting by Rule

Instead of setting a specific day number, you sometimes need to apply a rule such as the first day of the month, last day of the month, or next Monday:

```java
LocalDate day = LocalDate.of(2026, 10, 24); // Saturday
LocalDate first = day.with(TemporalAdjusters.firstDayOfMonth());
LocalDate last = day.with(TemporalAdjusters.lastDayOfMonth());
LocalDate nextMonday = day.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
```

This is an illustrative snippet inside a method, requiring `import java.time.LocalDate;`, `import java.time.DayOfWeek;`, and `import java.time.temporal.TemporalAdjusters;`. The results are `2026-10-01`, `2026-10-31`, and `2026-10-26`, respectively.

Compare two rules that are easy to confuse:

- `TemporalAdjusters.next(MONDAY)` selects the **Monday after the input date**, even if the input date is already a Monday.
- `TemporalAdjusters.nextOrSame(MONDAY)` selects the Monday **on or after** the input date; if the input date is already a Monday, it keeps that date.

`TemporalAdjuster` also lets you encapsulate custom business date-time rules. A custom adjuster must handle the `Temporal` types it receives appropriately; when rules are complex, such as "next business day," you need to account for public holidays as well, not just Saturdays and Sundays.

## 5. The plus...() Family: Adding an Amount by Unit

Specific methods express intent clearly:

```java
LocalDate date = LocalDate.of(2024, 1, 31);
LocalDate tomorrow = date.plusDays(1);       // 2024-02-01
LocalDate nextWeek = date.plusWeeks(1);      // 2024-02-07
LocalDate nextMonth = date.plusMonths(1);    // 2024-02-29
LocalDate nextYear = date.plusYears(1);      // 2025-01-31

LocalDateTime start = LocalDateTime.of(2024, 6, 10, 9, 30);
LocalDateTime later = start.plusHours(2).plusMinutes(15);
// 2024-06-10T11:45
```

The illustrative snippet above requires `import java.time.LocalDate;` and `import java.time.LocalDateTime;`. Addition handles day, month, and year boundaries according to the object's rules. For instance, `2024-01-31 + 1 month` becomes `2024-02-29` (a leap year) rather than throwing an error.

The general form `plus(long amountToAdd, TemporalUnit unit)` accepts units such as `ChronoUnit.DAYS`, `MONTHS`, `HOURS`, `MINUTES`, `SECONDS`, and `NANOS` **if the object supports them**.

```java
LocalDate result = LocalDate.of(2024, 1, 31)
        .plus(2, ChronoUnit.MONTHS); // 2024-03-31
```

This is an illustrative snippet with `import java.time.LocalDate;` and `import java.time.temporal.ChronoUnit;`. A `LocalDate` cannot call `plusHours(2)` because it has no time/hour component; calling `plus(2, ChronoUnit.HOURS)` throws an exception because the unit is unsupported.

The `plus` family also has `plus(TemporalAmount amount)`. For example:

```java
LocalDate deadline = LocalDate.of(2024, 1, 31);
LocalDate afterPeriod = deadline.plus(Period.ofMonths(1)); // 2024-02-29

Instant instant = Instant.parse("2024-01-01T00:00:00Z");
Instant laterInstant = instant.plus(Duration.ofMinutes(90));
// 2024-01-01T01:30:00Z
```

This is an illustrative snippet with `import java.time.LocalDate;`, `import java.time.Period;`, `import java.time.Instant;`, and `import java.time.Duration;`. `Period` suits calendar quantities (years, months, days), while `Duration` suits time-based quantities in seconds/nanoseconds. Do not use `Instant.plus(1, ChronoUnit.MONTHS)`: a pure instant has no calendar/time-zone context to know how many seconds "one month later" is.

## 6. The minus...() Family: Subtracting an Amount by Unit

`minus...()` is symmetric to `plus...()` in most use cases:

```java
LocalDate date = LocalDate.of(2024, 3, 1);
LocalDate previousDay = date.minusDays(1);     // 2024-02-29
LocalDate previousMonth = date.minusMonths(1); // 2024-02-01
LocalDate previousYear = date.minusYears(1);   // 2023-03-01

LocalTime clock = LocalTime.of(0, 15);
LocalTime earlier = clock.minusMinutes(30);    // 23:45
```

This is an illustrative snippet requiring `import java.time.LocalDate;` and `import java.time.LocalTime;`. `LocalTime` only represents time of day; when subtracting across midnight, the result wraps around within 24 hours **without retaining information about the previous day**. To preserve the date, use `LocalDateTime` or a time-zone-aware type.

The general forms:

```java
LocalDate date = LocalDate.of(2024, 3, 1);
LocalDate previous = date.minus(2, ChronoUnit.WEEKS);
LocalDate withPeriod = date.minus(Period.ofMonths(1));
```

This illustrative snippet requires `import java.time.LocalDate;`, `import java.time.Period;`, and `import java.time.temporal.ChronoUnit;`.

Adding a negative amount generally behaves like subtracting a positive amount and vice versa—for example, `date.plusDays(-3)` produces the same result as `date.minusDays(3)` within the valid range. However, be careful with `Long.MIN_VALUE` and representable date bounds: do not implement `minusDays(n)` as `plusDays(-n)` for arbitrary `long` values because `-Long.MIN_VALUE` overflows. Call the `minus...()` API directly to match the intended semantics.

## 7. Immutability When Chaining: Order Matters

A chain like:

```java
LocalDate result = start
        .withDayOfMonth(1)
        .plusMonths(1)
        .minusDays(2);
```

is evaluated **from left to right**: the value returned by each step becomes the input to the next step. `start` itself remains unchanged. You can split it into separate variables for debugging and meaningful naming:

```java
LocalDate firstDayThisMonth = start.withDayOfMonth(1);
LocalDate firstDayNextMonth = firstDayThisMonth.plusMonths(1);
LocalDate dueDate = firstDayNextMonth.minusDays(2);
```

These are two illustrative snippets inside a method where `start` is a valid `LocalDate`, requiring `import java.time.LocalDate;`. Naming each step is clearer when business rules are complex.

**Month-based calculations are not always associative in the intuitive way**, due to end-of-month clamping. For example, starting from `2024-01-31`:

```java
LocalDate start = LocalDate.of(2024, 1, 31);

System.out.println(start.plusMonths(1));               // 2024-02-29
System.out.println(start.plusMonths(1).plusMonths(1)); // 2024-03-29
System.out.println(start.plusMonths(2));               // 2024-03-31
```

This is an illustrative snippet inside a method with `import java.time.LocalDate;`. The first `+1 month` clamps 31 to 29 when crossing February; the next step uses **day 29** as its base, whereas `+2 months` directly from January 31 keeps day 31 in March.

Therefore, for recurring monthly billing schedules, compute each cycle from the **original anchor date plus n months**, or explicitly define an "end-of-month" rule, rather than always chaining from the previous cycle's result and assuming they are equivalent.

## 8. Complete Java 17+ Example: Immutability, with, plus, minus

Save the file **`ImmutableDateTimeDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;

public class ImmutableDateTimeDemo {
    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2024, 1, 31);

        LocalDate firstDay = original.withDayOfMonth(1);
        LocalDate oneMonthLater = original.plusMonths(1);
        LocalDate threeDaysEarlier = firstDay.minusDays(3);

        System.out.println("original = " + original);
        System.out.println("firstDay = " + firstDay);
        System.out.println("oneMonthLater = " + oneMonthLater);
        System.out.println("threeDaysEarlier = " + threeDaysEarlier);
        System.out.println("original again = " + original);

        LocalDateTime meeting = LocalDateTime.of(2024, 6, 10, 9, 30);
        LocalDateTime rescheduled = meeting
                .withHour(14)
                .plusDays(2)
                .minusMinutes(15);

        System.out.println("meeting = " + meeting);
        System.out.println("rescheduled = " + rescheduled);

        LocalDate saturday = LocalDate.of(2026, 10, 24);
        LocalDate nextMonday = saturday.with(
                TemporalAdjusters.next(DayOfWeek.MONDAY));
        System.out.println("nextMonday = " + nextMonday);
    }
}
```

Run with Java 17+:

```bash
javac ImmutableDateTimeDemo.java
java ImmutableDateTimeDemo
```

Deterministic output:

```text
original = 2024-01-31
firstDay = 2024-01-01
oneMonthLater = 2024-02-29
threeDaysEarlier = 2023-12-29
original again = 2024-01-31
meeting = 2024-06-10T09:30
rescheduled = 2024-06-12T14:15
nextMonday = 2026-10-26
```

Explanation:

1. `firstDay`, `oneMonthLater`, and `threeDaysEarlier` are new values, while `original` remains unchanged.
2. `plusMonths(1)` from January 31, 2024 lands on February 29, 2024 because February in a leap year has no 31st day.
3. When rescheduling the meeting, `withHour(14)` sets the hour to 14, `plusDays(2)` moves to June 12, and `minusMinutes(15)` changes minute 30 to 15.
4. `next(MONDAY)` finds the next Monday after Saturday, October 24, 2026.

## 9. Crossing DST: plusDays(1) Can Differ from plusHours(24)

This is a critical distinction for `ZonedDateTime` when a time zone changes its offset due to daylight saving time rules. `plusDays(1)` operates by **local calendar days**; `plusHours(24)` operates by **24 elapsed hours** on the timeline. The two results can differ during a DST transition.

Save the file **`DstAdjustmentDemo.java`**:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstAdjustmentDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        ZonedDateTime before = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, zone);

        ZonedDateTime nextCalendarDay = before.plusDays(1);
        ZonedDateTime after24Hours = before.plusHours(24);

        System.out.println("before = " + before);
        System.out.println("plusDays(1) = " + nextCalendarDay);
        System.out.println("plusHours(24) = " + after24Hours);
        System.out.println("elapsedHours = "
                + Duration.between(before, nextCalendarDay).toHours());
    }
}
```

Compile and run:

```bash
javac DstAdjustmentDemo.java
java DstAdjustmentDemo
```

Output according to the New York time zone rules for March 2024:

```text
before = 2024-03-09T12:00-05:00[America/New_York]
plusDays(1) = 2024-03-10T12:00-04:00[America/New_York]
plusHours(24) = 2024-03-10T13:00-04:00[America/New_York]
elapsedHours = 23
```

On the night of March 10, 2024 in New York, clocks sprang forward from 02:00 to 03:00. Going from **12:00 the previous day to 12:00 the next day on the local calendar** is only 23 elapsed hours, whereas adding an exact 24 hours reaches 13:00. Therefore:

- For "tomorrow at the same local time" → typically use `zoned.plusDays(1)`.
- For "after an exact 24 real hours" → use `zoned.plusHours(24)` or `zoned.plus(Duration.ofHours(24))`.
- `Period.ofDays(1)` represents a calendar day; `Duration.ofDays(1)` always represents 24 hours in seconds. With `ZonedDateTime`, they can produce two different instants.

When using `withHour(...)` or changing the date on a `ZonedDateTime` and landing on a local time that **does not exist** in a DST gap, Java must adjust the result to obtain a valid instant; in an overlap, there can be two valid offsets. Do not assume every combination of "date + local time + ZoneId" maps uniquely to a single instant. For appointment scheduling, you must define the behavior in gap/overlap regions.

Do not apply DST reasoning to `LocalDateTime` when no `ZoneId` is attached: `LocalDateTime` only holds calendar/time components and does not define an offset or an instant on the timeline.

## 10. Different java.time Classes Support Different Operations

| Type | Field Replacement with `with` | Typical Add/Subtract | Limits to Remember |
| --- | --- | --- | --- |
| `LocalDate` | `withYear`, `withMonth`, `withDayOfMonth`, calendar adjusters | `plusDays`, `plusMonths`, `minusYears` | No time, offset, or zone |
| `LocalTime` | `withHour`, `withMinute`, `withNano` | `plusHours`, `minusSeconds` | Wraps around 24 hours, does not track date |
| `LocalDateTime` | Date and time fields | `plusDays`, `plusHours`, `minusMinutes` | Not DST-aware without a zone |
| `ZonedDateTime` | Date/time fields, zone/offset adjustments | Add calendar days or time durations | Must account for DST gaps/overlaps |
| `OffsetDateTime` | Date/time fields and offset | Add/subtract date/time | Carries a fixed offset in the value, not full `ZoneId` rules |
| `Instant` | Supported instant fields | `plusSeconds`, `plusMillis`, `minusNanos` | Cannot add "calendar months" without a zone |
| `Duration` | `withSeconds`, `withNanos` | `plusSeconds`, `minusMillis`, add/subtract `Duration` | Elapsed duration, not calendar date/time |
| `Period` | `withYears`, `withMonths`, `withDays` | `plusYears`, `minusMonths`, add/subtract `Period` | Years-months-days amount, not a fixed number of seconds |

In particular, `Period.withDays(5)` means **replace the days component with 5**, not convert the period to "5 days total." For example, `Period.of(1, 2, 3).withDays(5)` is `P1Y2M5D`, whereas `Period.of(1, 2, 3).plusDays(5)` is `P1Y2M8D`. Note that `Period` components can carry independent signs; `Period` does not automatically normalize all combinations into a single day count because month lengths vary.

Similarly, `Duration.withNanos(500_000_000)` replaces the nanosecond-of-second part; it **does not add** 500 million nanoseconds. Choosing the right quantity type is the first step before using these method families.

## 11. Validation, Exceptions, and Overflow

Immutable operations can still fail:

- **Invalid field value:** `withDayOfMonth(32)` or `withHour(24)` is rejected with `DateTimeException`.
- **Unsupported field or unit:** for example, `LocalDate.now().plus(1, ChronoUnit.HOURS)` throws `UnsupportedTemporalTypeException` (a subclass of `DateTimeException`).
- **Exceeding representable range:** for example, `LocalDate.MAX.plusDays(1)` cannot produce a valid value; you may encounter `DateTimeException` or `ArithmeticException` depending on the API and operation.
- **Numeric overflow:** some conversions or multiplications with large amounts can throw `ArithmeticException`, especially when input comes from external sources.

Save the file **`InvalidAdjustmentDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

public class InvalidAdjustmentDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);

        try {
            date.withDayOfMonth(30);
        } catch (DateTimeException ex) {
            System.out.println("Invalid February day");
        }

        try {
            date.plus(1, ChronoUnit.HOURS);
        } catch (DateTimeException ex) {
            System.out.println("Unsupported hour unit");
        }

        System.out.println("date remains = " + date);
    }
}
```

Compile with `javac InvalidAdjustmentDemo.java` and run `java InvalidAdjustmentDemo`:

```text
Invalid February day
Unsupported hour unit
date remains = 2024-02-29
```

Because the object is immutable, failed calls do not corrupt `date`. Still, you should **validate user input** before scheduling, and catch exceptions at an appropriate level to provide useful error messages rather than silently turning invalid values into an arbitrary date.

## 12. Rules for Real-World Code

1. **Always use the return value.** A standalone `orderDate.plusDays(7);` call is almost certainly a bug. Assign the result or return it from the method.
2. **Use `with...()` when the requirement says "set to."** "Set due date to the 1st" → `withDayOfMonth(1)`; "extend by 1 month" → `plusMonths(1)`.
3. **Distinguish calendar units from elapsed durations.** Calendar-based deadlines in months/days do not automatically equal a fixed number of hours; this is even more critical across DST.
4. **Watch the chaining order.** With end-of-month dates, `plusMonths(1).plusMonths(1)` can differ from `plusMonths(2)`.
5. **Preserve temporal context.** Use `LocalDate` for a pure date, `ZonedDateTime` for time-zone-aware scheduling, and `Instant` for an absolute timestamp. Do not infer a zone from `LocalDateTime`.
6. **Use adjusters to express rules.** `firstDayOfMonth()`, `lastDayOfMonth()`, and `nextOrSame(...)` are clearer than manually adding/subtracting "magic" numbers.
7. **Avoid identity comparison.** `before.equals(after)` checks value equality; `before == after` only compares references.
8. **Use fixed inputs in tests.** The examples use `of(...)` instead of `now()` so results do not vary with execution time; business logic should accept an injected `Clock` for controlled testing.
9. **Test boundary cases.** Include Feb 28, Feb 29 in leap years, Apr 30, Jan 31, year transitions, DST transitions, 23:59, and out-of-range fields.
10. **Do not confuse immutability with "always error-free."** Immutability protects the original object, but month-end rules, DST zones, and value bounds still require proper design.

## 13. Self-Check Exercises

**Question 1.** Given `LocalDate d = LocalDate.of(2024, 1, 31);`, `d.plusMonths(1);` is called without assigning the result. After this statement, what is `d`?

**Answer:** `2024-01-31`; the return value was discarded.

**Question 2.** Starting from January 31, 2024, what do `withDayOfMonth(1)`, `plusDays(1)`, and `plusMonths(1)` return, respectively?

**Answer:** `2024-01-01`, `2024-02-01`, `2024-02-29`.

**Question 3.** Starting from January 31, 2024, are `plusMonths(2)` and `plusMonths(1).plusMonths(1)` equal?

**Answer:** No. The first produces `2024-03-31`; the second produces `2024-03-29` because the intermediate step through February clamps day 31 down to 29.

**Question 4.** Why does `ZonedDateTime.plusDays(1)` differ from `ZonedDateTime.plusHours(24)` across a DST transition?

**Answer:** One adds by **local calendar days**, while the other adds **24 elapsed hours**. A day with a DST transition can be 23 or 25 hours long.

**Question 5.** What should you use to find the Monday **today or next**?

**Answer:** `date.with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY))`. If you use `next(...)` on a date that is already Monday, the result will be the Monday of the following week.

**Conclusion:** In `java.time`, `with...()` **replaces a component value or applies an adjustment rule**, `plus...()` **adds**, and `minus...()` **subtracts**. All three return an immutable date-time value; choosing the right date-time type, unit, and boundary rules is what ensures your result matches the business logic.