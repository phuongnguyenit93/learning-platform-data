# Creating a `LocalDateTime` from Components or from `LocalDate` and `LocalTime`

In Java, a point in time on a **local wall clock** is typically described by year, month, day and hour, minute, second. For example, a scheduling form receives the date **29/02/2024** and the time **14:05:06.123**. To combine this information into a single object, use `java.time.LocalDateTime`:

```java
LocalDateTime meeting = LocalDateTime.of(2024, 2, 29, 14, 5, 6, 123_000_000);
```

Or, when you already have separate date and time objects:

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);
LocalDateTime meeting = LocalDateTime.of(date, time);
```

The short snippets above require `import java.time.*;` when placed inside a Java method or class. **Both approaches produce the same value**: `2024-02-29T14:05:06.123`.

What to keep in mind from the start: `LocalDateTime` only holds a **local date and time**, with no `ZoneId`, UTC offset, or `Instant`. That is the difference between “14:05 on February 29” and “an event occurring at a unique instant in the world”.

## 1. Understanding the Structure of `LocalDateTime`

`LocalDateTime` belongs to the `java.time` package, introduced in Java 8 and fully available in Java 17+. It represents a **date-time in the ISO-8601 calendar system** without a time zone. You can visualize it as:

```text
LocalDate        2024-02-29
LocalTime        14:05:06.123
                      │
          LocalDateTime.of(date, time)
                      ↓
LocalDateTime    2024-02-29T14:05:06.123
```

The components and their meanings:

| Component | Example | Common valid values |
| --- | --- | --- |
| Year (`year`) | `2024` | Valid year values within the supported range of the ISO calendar in `java.time`, including negative years and year 0 under astronomical year numbering. |
| Month (`month`) | `2` or `Month.FEBRUARY` | Number 1–12 or a `Month` enum. |
| Day of month (`dayOfMonth`) | `29` | Depends on month and year; February in a leap year has day 29. |
| Hour (`hour`) | `14` | 0–23. |
| Minute (`minute`) | `5` | 0–59. |
| Second (`second`) | `6` | 0–59. |
| Nanosecond (`nanoOfSecond`) | `123_000_000` | 0–999,999,999; 123 million ns = 123 ms. |

`LocalDateTime` is designed to be **immutable** and safe for sharing values across threads: changing the date, time, or adding duration returns a new value object. When creating via `of(...)`, Java validates the date and time against the calendar: `2024-02-29` is valid because 2024 is a leap year, whereas `2025-02-29` is invalid.

The default string format uses the letter `T` between the date and time per ISO-8601, e.g., `2024-02-29T14:05`. If seconds or the fractional part are 0, the string representation may omit those parts; the value itself still has all fields set to 0.

## 2. Creating Directly from Fields with `LocalDateTime.of(...)`

When data starts as integer values such as year, month, day, hour, and minute, the clearest approach is one of the following overloads:

| Representative overload | Type / Meaning |
| --- | --- |
| `LocalDateTime.of(year, month, day, hour, minute)` | Creates from year, **numeric month**, day, hour, and minute; second and nanosecond are 0. |
| `LocalDateTime.of(year, month, day, hour, minute, second)` | Adds second; nanosecond is 0. |
| `LocalDateTime.of(year, month, day, hour, minute, second, nano)` | Adds nanosecond precision. |
| `LocalDateTime.of(year, Month.JANUARY, day, hour, minute)` | Uses the `Month` enum instead of a month number. |
| `LocalDateTime.of(year, Month.JANUARY, day, hour, minute, second)` | `Month` enum and second. |
| `LocalDateTime.of(year, Month.JANUARY, day, hour, minute, second, nano)` | `Month` enum, second, and nanosecond. |

Examples (requires `import java.time.*;`):

```java
LocalDateTime a = LocalDateTime.of(2024, 2, 29, 14, 5);
LocalDateTime b = LocalDateTime.of(2024, Month.FEBRUARY, 29, 14, 5);
LocalDateTime c = LocalDateTime.of(2024, 2, 29, 14, 5, 6);
LocalDateTime d = LocalDateTime.of(
        2024, Month.FEBRUARY, 29, 14, 5, 6, 123_000_000
);
```

Values `a` and `b` are both `2024-02-29T14:05`; `c` is `2024-02-29T14:05:06`, and `d` is `2024-02-29T14:05:06.123`.

**When to use numeric months:** the input already provides separate fields or you want a short, clear example. **When to use `Month`:** the code has a hardcoded month and you want to avoid 1–12 confusion, such as `Month.DECEMBER` being clearer than `12`. `Month` does not use `0` for January.

**Time boundaries:** hour `24` is invalid in `LocalDateTime.of(...)`; 00:00 of the next day must be written as **next day + hour 00:00**. Second `60` is also invalid in this API; do not expect `of(...)` to handle leap seconds by allowing 60.

## 3. Creating from `LocalDate` and `LocalTime` with `of(date, time)`

When an application separates date and time into two independent pieces of data, construct each part with the appropriate type and combine them:

```java
LocalDate deliveryDate = LocalDate.of(2025, 10, 24);
LocalTime deliveryTime = LocalTime.of(9, 30);
LocalDateTime deliveryAt = LocalDateTime.of(deliveryDate, deliveryTime);
```

The result is `2025-10-24T09:30`. This approach is often more natural than breaking components into six separate numbers when:

- A form has two separate inputs, one for picking the date and one for picking the time.
- Business logic already has a run date (`LocalDate`) and a daily time (`LocalTime`).
- A recurring schedule uses the **same local time** while changing the date on each execution.
- You want to reuse date validation logic and time validation logic before combining them.

This method takes exact `LocalDate` and `LocalTime` objects. Java performs no automatic time-zone conversion, and it does not read the system clock to fill in missing fields. Therefore, using `LocalDateTime.of(date, time)` when you already have both values gives direct meaning, better readability, and easier testing.

### Equivalent ways to write it

Given valid `date` and `time` values, the following produce the exact same date-time value:

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(14, 5);

LocalDateTime fromOf = LocalDateTime.of(date, time);
LocalDateTime fromDate = date.atTime(time);
LocalDateTime fromTime = time.atDate(date);
```

- `LocalDateTime.of(date, time)` emphasizes **creating a date-time object from two components**.
- `date.atTime(time)` emphasizes **an existing date having a time attached to it**.
- `time.atDate(date)` emphasizes **an existing time having a date attached to it**.

All three create a `LocalDateTime`, and none implicitly carries time-zone information. Choose the one that best expresses the data source; there is no need to switch back and forth purely for style. Within a codebase, using one consistently helps readers.

## 4. Complete Java 17+ Example: Comparing Creation Methods and Checking Immutability

Create `LocalDateTimeCreationDemo.java` matching the public class name:

```java
import java.time.*;

public class LocalDateTimeCreationDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);

        LocalDateTime fromObjects = LocalDateTime.of(date, time);
        LocalDateTime fromNumbers =
                LocalDateTime.of(2024, 2, 29, 14, 5, 6, 123_000_000);
        LocalDateTime fromAtTime = date.atTime(time);

        System.out.println("From objects : " + fromObjects);
        System.out.println("From numbers : " + fromNumbers);
        System.out.println("From atTime  : " + fromAtTime);
        System.out.println("All equal    : "
                + (fromObjects.equals(fromNumbers)
                && fromNumbers.equals(fromAtTime)));

        System.out.println("Only hour/min: "
                + LocalDateTime.of(2024, 2, 29, 14, 5));
        System.out.println("Midnight     : " + date.atStartOfDay());

        LocalDateTime next = fromObjects.plusDays(1);
        System.out.println("Original     : " + fromObjects);
        System.out.println("Plus day     : " + next);

        try {
            LocalDateTime.of(2025, 2, 29, 10, 0);
        } catch (DateTimeException e) {
            System.out.println("Invalid date : DateTimeException");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LocalDateTimeCreationDemo.java
java LocalDateTimeCreationDemo
```

Verified output:

```text
From objects : 2024-02-29T14:05:06.123
From numbers : 2024-02-29T14:05:06.123
From atTime  : 2024-02-29T14:05:06.123
All equal    : true
Only hour/min: 2024-02-29T14:05
Midnight     : 2024-02-29T00:00
Original     : 2024-02-29T14:05:06.123
Plus day     : 2024-03-01T14:05:06.123
Invalid date : DateTimeException
```

**Analysis:**

1. `fromObjects`, `fromNumbers`, and `fromAtTime` are equal according to `equals()` because they contain the same date, hour, second, and nanosecond.
2. Using the overload that only takes hour and minute sets seconds and nanoseconds to 0. `LocalDateTime.toString()` therefore displays `2024-02-29T14:05`; it is not a separate type lacking seconds.
3. `date.atStartOfDay()` creates a `LocalDateTime` at midnight **without a time zone**. It is equivalent to `date.atTime(LocalTime.MIDNIGHT)` in date-time value. When you need the valid start of day in a specific zone, use the `date.atStartOfDay(zone)` overload, which returns a `ZonedDateTime`.
4. `fromObjects.plusDays(1)` produces March 1 because after February 29 in a leap year comes March 1, while keeping the time `14:05:06.123`. The `fromObjects` variable remains unchanged because the object is immutable.
5. February 29, 2025 cannot be created because 2025 is not a leap year. `LocalDateTime.of(...)` throws `DateTimeException` immediately upon creation instead of rolling over to March 1.

In business code, if a user enters an invalid date, you should catch or validate the exception at the input boundary and display a specific message. Do not mask errors by silently rounding to another date the user did not select.

## 5. Controlling Precision for Hours, Minutes, Seconds, and Nanoseconds

The time component is represented by `LocalTime`, so `LocalDateTime` has the same granularity down to **nanoseconds**. Some creation examples:

```java
LocalDateTime minutePrecision =
        LocalDateTime.of(2025, 6, 10, 8, 30);
LocalDateTime secondPrecision =
        LocalDateTime.of(2025, 6, 10, 8, 30, 15);
LocalDateTime millisecondPrecision =
        LocalDateTime.of(2025, 6, 10, 8, 30, 15, 250_000_000);
```

The values are `2025-06-10T08:30`, `2025-06-10T08:30:15`, and `2025-06-10T08:30:15.250`, respectively. One millisecond equals **1,000,000 nanoseconds**, so 250 ms is `250_000_000` ns, not `250` ns.

Do not infer from how `toString()` trims trailing fractional digits that the data type only stores milliseconds. `LocalDateTime` has representational precision down to nanoseconds, though that **does not mean** the computer clock or database always measures or stores 1 ns accuracy. `of(...)` simply constructs a value with the specified components; it does not observe a real clock.

## 6. Converting UI Input Fields into Objects

A common scenario in applications: the UI sends year, month, day, and hour/minute in separate fields. You can map them directly after validation:

```java
int year = 2025;
int month = 10;
int day = 24;
int hour = 9;
int minute = 30;

LocalDateTime appointment =
        LocalDateTime.of(year, month, day, hour, minute);
```

If a form provides separate **date string** and **time string** inputs, parse each string using its expected format and then combine them:

```java
LocalDate date = LocalDate.parse("2025-10-24");
LocalTime time = LocalTime.parse("09:30");
LocalDateTime appointment = LocalDateTime.of(date, time);
```

These two snippets belong inside a method with `import java.time.*;` and are not standalone Java files. The string data here uses ISO-8601. If the input is a date in Vietnamese format `24/10/2025`, you can use an explicit `DateTimeFormatter`:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
LocalDate date = LocalDate.parse("24/10/2025", formatter);
LocalTime time = LocalTime.parse("09:30");
LocalDateTime appointment = date.atTime(time);
```

The snippet above requires `import java.time.format.DateTimeFormatter;` and `import java.time.*;`. `DateTimeFormatter` belongs to a separate topic on parsing and formatting; the core takeaway of this lesson is **once you have `LocalDate` and `LocalTime`, combine them with `of(date, time)` or `date.atTime(time)`**.

Keeping date and time as typed values avoids ad-hoc string concatenation like `dateText + "T" + timeText` when you still need to validate input. If a form is missing a required field, prompt the user to provide it; do not default to `LocalDate.now()` or `LocalTime.now()` unless business rules allow it.

## 7. Distinguishing Value Creation from Getting the “Current Date and Time”

`LocalDateTime.of(...)` creates a value **determined by its arguments**; it does not read the system clock. Comparison:

| Creation method | Data source | Characteristics |
| --- | --- | --- |
| `LocalDateTime.of(2025, 10, 24, 9, 30)` | Passed-in numeric fields | Creates a fixed value, always the same. |
| `LocalDateTime.of(date, time)` | Two `LocalDate` and `LocalTime` objects | Combines known date and time. |
| `date.atTime(time)` | Known date and known time | Natural expression when starting from a date. |
| `LocalDateTime.parse("2025-10-24T09:30")` | Validly formatted string | Used when the source is ISO-8601 text. |
| `LocalDateTime.now()` | System clock and default time zone | Value changes depending on call time and environment. |
| `LocalDateTime.now(zone)` | System clock in the specified zone | Current local time there, though the result still carries no zone info. |
| `LocalDateTime.now(clock)` | Passed-in `Clock` | Convenient for testing with a fixed or mock clock. |

When writing tests for date-time logic, prefer values created with `of(...)` or `Clock.fixed(...)` instead of tests that depend on the actual run date. When deploying applications, note that `LocalDateTime.now()` uses the process's default time zone; results may differ between a developer machine and a CI container.

In particular, if the requirement is “at what **exact instant** was the order created”, `Instant.now()` directly expresses that event meaning. `LocalDateTime.now()` describes the system's local date-time at that moment but drops the zone information from the result.

## 8. Why `LocalDateTime.of(...)` Does Not Determine a UTC Instant

Creating a date-time from fields or combining `LocalDate`/`LocalTime` **does not select a time zone**. For example, `2025-10-24T09:30` in Vietnam and `2025-10-24T09:30` in New York correspond to different instants. To convert to an `Instant`, you must specify a zone or offset according to business requirements:

```java
LocalDate date = LocalDate.of(2025, 10, 24);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime localAppointment = LocalDateTime.of(date, time);

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zonedAppointment = localAppointment.atZone(vietnam);
Instant instant = zonedAppointment.toInstant();
```

This is an illustrative snippet requiring `import java.time.*;`. In this case, the zoned date-time result is `2025-10-24T09:30+07:00[Asia/Ho_Chi_Minh]`, and the `Instant` is `2025-10-24T02:30:00Z`.

**Note:** A `ZoneId` such as `America/New_York` contains regional time-zone rules, including DST in transition years; a `ZoneOffset` such as `-05:00` only states a fixed offset. If scheduling months ahead in a city's local time, choose the appropriate `ZoneId` to apply regional rules instead of assuming a constant offset.

### Missing or repeated local times due to DST

Java can still create a `LocalDateTime` from calendar-valid fields even when a given zone has no corresponding instant. `of(...)` does not know which zone applies, so it cannot determine on its own whether that local time exists at the scheduling location.

- **Gap:** in New York, `2024-03-10T02:30` does not exist on the local clock because clocks spring forward to daylight saving time.
- **Overlap:** in New York, `2024-11-03T01:30` occurs twice when clocks fall back to standard time; once at offset `-04:00`, and again at `-05:00`.

Below is a standalone verification program. Create `LocalDateTimeZoneDemo.java`:

```java
import java.time.*;

public class LocalDateTimeZoneDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                LocalDate.of(2024, 11, 3),
                LocalTime.of(1, 30)
        );

        System.out.println("Gap local       : " + gap);
        System.out.println("Gap offsets     : "
                + zone.getRules().getValidOffsets(gap));
        System.out.println("Gap resolved    : " + gap.atZone(zone));
        System.out.println("Overlap local   : " + overlap);
        System.out.println("Overlap offsets : "
                + zone.getRules().getValidOffsets(overlap));
        System.out.println("Earlier instant : "
                + overlap.atZone(zone).toInstant());
        System.out.println("Later instant   : "
                + overlap.atZone(zone).withLaterOffsetAtOverlap().toInstant());
    }
}
```

```bash
javac LocalDateTimeZoneDemo.java
java LocalDateTimeZoneDemo
```

Verified output from running the program:

```text
Gap local       : 2024-03-10T02:30
Gap offsets     : []
Gap resolved    : 2024-03-10T03:30-04:00[America/New_York]
Overlap local   : 2024-11-03T01:30
Overlap offsets : [-04:00, -05:00]
Earlier instant : 2024-11-03T05:30:00Z
Later instant   : 2024-11-03T06:30:00Z
```

Both `gap` and `overlap` are successfully created with `LocalDateTime.of(...)`. However, `getValidOffsets(gap)` returns an empty list because that time **does not exist** in the zone, and `atZone(zone)` by default pushes the time past the gap. For `overlap`, there are two valid offsets, producing two `Instant` values one hour apart.

Therefore, when building real appointments or zoned transactions, after creating the `LocalDateTime` you must add a **DST policy**: reject nonexistent times, adjust automatically, or let the user choose between the two overlapping occurrences. Do not treat `LocalDateTime.of(...)` as complete validation for a zoned appointment.

## 9. Edge Cases and Common Mistakes When Creating

1. **Months start at 1, not 0.** `LocalDateTime.of(2025, 0, 1, 9, 0)` is an invalid value; there is no month 0.
2. **The day must be valid for the month and year.** `LocalDateTime.of(2025, 2, 29, 9, 0)` fails; `LocalDateTime.of(2024, 2, 29, 9, 0)` is valid. Java checks leap years.
3. **Valid hours are 0–23, minutes/seconds 0–59.** `24:00`, `09:60`, or second `60` are not accepted by the integer overloads. For midnight of the next day, add one day and use `00:00`.
4. **Nanoseconds are not milliseconds.** Passing `123` for `nanoOfSecond` is only 123 ns, not 123 ms. 123 ms must be written as `123_000_000` ns.
5. **Do not pass `null` for missing data.** `LocalDateTime.of(date, null)` will not supply a default time; for methods requiring objects, required parameters must have proper values.
6. **Creating a date-time does not apply a time zone.** `LocalDateTime.of(...)` does not attach `Asia/Ho_Chi_Minh` just because the application runs in Vietnam.
7. **Do not use `LocalDateTime` as a global timestamp.** The same value can correspond to different `Instant` values depending on the zone; use `Instant` or an offset/zoned type when the business logic requires a real point in time.
8. **Arithmetic does not mutate an already-created object.** `appointment.plusDays(1)` returns a new object. To keep the result, assign it to a new variable or reassign the current variable.
9. **Do not build ad-hoc strings when the API provides typed constructors.** If the source has numeric fields, create directly; if the source is text, parse with the proper format and combine objects.
10. **Check time-zone/DST rules when applying a zone.** `of(...)` only validates calendar/clock values and does not know whether a city skips or repeats that local time.
11. **The start of a day is not always “24 hours before the next start of day” in real elapsed time.** `LocalDate.atStartOfDay(zone)` follows zone rules; between two day starts there may be 23 or 25 hours across DST.
12. **Do not assume systems store full nanosecond precision.** When writing to a database or sending JSON, check the precision and format supported by the library, driver, or API contract; you may need to round or normalize per business rules.

### Handling invalid data

For invalid input, `of(...)` throws `DateTimeException` or an appropriate subclass. This helps catch errors early. At the UI/API layer, validate input and translate the exception into a message such as “February 29 does not exist in 2025” instead of returning a stack trace to the user.

If the date and time fields come from independent steps, constructing `LocalDate` and `LocalTime` separately helps pinpoint which part failed before combining. If a form already provides valid numbers, calling `LocalDateTime.of(...)` directly is clear enough.

## 10. Practical Applications and Exercises

| Task | Recommended creation | Reason |
| --- | --- | --- |
| Meeting schedule from year/month/day, hour/minute dropdowns | `LocalDateTime.of(year, month, day, hour, minute)` | Inputs are already numeric components. |
| UI with a date picker and a time picker | `LocalDateTime.of(date, time)` | The two components are already `LocalDate` and `LocalTime`. |
| Fixed due date at 17:00 | `dueDate.atTime(17, 0)` | Date is known; only the time needs to be added. |
| Shift starting at a familiar time on a new date | `shiftTime.atDate(shiftDate)` | Starting from an existing `LocalTime`. |
| Midnight of a day without needing a time zone | `date.atStartOfDay()` | Returns `LocalDateTime` at `00:00`. |
| Scheduled run at 09:00 in New York | `date.atTime(9, 0).atZone(zone)` with DST check | Must select zone and transition rules. |
| Recording timestamp when an order is created | `Instant.now()` | Goal is the actual event instant, not just local date-time. |

**Exercise 1 — Compare two creation approaches.** Create `2026-01-15T08:45` using `of(int, ...)` and `of(LocalDate, LocalTime)`, then use `equals()` to verify they are equal.

```java
LocalDateTime a = LocalDateTime.of(2026, 1, 15, 8, 45);
LocalDate date = LocalDate.of(2026, 1, 15);
LocalTime time = LocalTime.of(8, 45);
LocalDateTime b = LocalDateTime.of(date, time);
// a.equals(b) == true
```

**Exercise 2 — Seconds and nanoseconds.** What are the second and nanosecond values of `LocalDateTime.of(2026, 1, 15, 8, 45)`?

**Answer:** Both are 0, even though `toString()` normally displays only `2026-01-15T08:45`.

**Exercise 3 — Scheduling on a leap day.** What is `2024-02-29T23:30` plus one day? Does it modify the original object?

**Answer:** `2024-03-01T23:30`. Calling `plusDays(1)` returns a new object; the original object is unchanged.

**Exercise 4 — Actual instant.** An appointment has `LocalDateTime.of(2025, 10, 24, 9, 30)`. Can we conclude that it is `2025-10-24T09:30Z`?

**Answer:** No. You need to know the offset or `ZoneId`. 09:30 in Vietnam on that day corresponds to `02:30Z`, while 09:30 in another zone may correspond to a different `Instant`.

**Exercise 5 — Overlapping time values.** Does `LocalDateTime.of(2024, 11, 3, 1, 30)` in New York always refer to a single instant?

**Answer:** No. On the day DST ends, 01:30 can occur twice, leading to two different `Instant` values if different offsets are chosen.

## Key Takeaways

`LocalDateTime.of(year, month, day, hour, minute, ...)` is used when you **already have the numeric components**; `LocalDateTime.of(date, time)` is used when you **already have `LocalDate` and `LocalTime`**. `date.atTime(time)` and `time.atDate(date)` are convenient expressions that produce the same result type. In all of the above, Java validates calendar/time values and returns an immutable object; **no method automatically assigns a time zone or determines an `Instant`**. Choose `ZoneId`/offset and a DST policy at the business step that requires determining an actual point in time.
