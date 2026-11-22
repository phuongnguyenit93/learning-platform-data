# Choosing Calendar-Based or Timeline-Based Calculations

When handling dates and times, Java needs to express the exact business intent: **preserving a calendar date/time** or **shifting by a fixed duration along the timeline**. These two operations can return different results when crossing Daylight Saving Time (DST), the end of a month, or the end of a year.

In `java.time`, the primary types are `LocalDate`, `LocalDateTime`, `ZonedDateTime`, `Instant`, `Period`, and `Duration`. Choose based on the semantics you need to preserve, not merely on the words "day", "hour", or "month" in the requirement.

## 1. Two Different Ways of Thinking

**Calendar-based calculations** preserve the meaning of calendar units such as days, months, years, or local time within a specific zone. Examples: "tomorrow at 09:00 in Hanoi", "add one month to an invoice", "the same time on the next business day".

**Timeline-based calculations** shift by a span of time with a fixed length. Examples: "in exactly 24 hours", "timeout after 30 seconds", "measure the interval between sending and receiving a request".

| Need | Suitable Type/API |
| --- | --- |
| Next calendar day | `LocalDate.plusDays(1)` |
| Next calendar month | `LocalDate.plusMonths(1)` or `Period.ofMonths(1)` |
| Same local time tomorrow in a zone | `ZonedDateTime.plusDays(1)` |
| Exactly 24 hours later | `Instant.plus(Duration.ofHours(24))` |
| 10-second timeout | `Duration.ofSeconds(10)` |
| Measure from start to end | `Duration.between(start, end)` |
| Repeat at 09:00 every day in a city | Date/`LocalTime` + `ZoneId` and DST policy |

**A calendar day is not always equivalent to 24 elapsed hours.** In a zone with DST, the actual elapsed time between noon on two consecutive calendar days can be 23 or 25 hours. Conversely, `Duration.ofDays(1)` is always equal to 86,400 seconds.

## 2. Distinguishing Period and Duration

`Period` represents a calendar-based amount in years, months, and days. `Duration` represents a time-based amount in seconds and nanoseconds.

| Characteristic | `Period` | `Duration` |
| --- | --- | --- |
| Meaning | Calendar-based years/months/days | Time span of fixed length |
| Example | `Period.ofMonths(1)` | `Duration.ofHours(24)` |
| Day unit | One calendar day | `Duration.ofDays(1)` is always 86,400 seconds |
| Month unit | Yes; applied according to a specific calendar | No fixed month in seconds |
| Suitable for | Due dates, next calendar day, calendar months/years | Timeouts, retry delays, elapsed time between two `Instant`s |

```java
import java.time.Duration;
import java.time.Period;

Period oneMonth = Period.ofMonths(1);
Period oneCalendarDay = Period.ofDays(1);
Duration twentyFourHours = Duration.ofHours(24);
Duration oneDurationDay = Duration.ofDays(1);

System.out.println(oneMonth);         // P1M
System.out.println(oneCalendarDay);   // P1D
System.out.println(twentyFourHours);  // PT24H
System.out.println(oneDurationDay);  // PT24H
```

This is an illustrative snippet to be placed inside a Java method. `Period.ofDays(1)` means one calendar day; `Duration.ofDays(1)` means 24 hours. `Period.ofMonths(1)` cannot be converted into a fixed number of seconds without a specific date/month and calendar rules.

## 3. Adding Days and Months with LocalDate

`LocalDate` holds only a calendar date, with no time of day or time zone. Use it when the problem is strictly about dates:

```java
import java.time.LocalDate;
import java.time.Period;

LocalDate invoiceDate = LocalDate.of(2024, 1, 31);

System.out.println(invoiceDate.plusDays(1));              // 2024-02-01
System.out.println(invoiceDate.plusMonths(1));            // 2024-02-29
System.out.println(invoiceDate.plus(Period.ofMonths(1))); // 2024-02-29
```

When adding months, if that day does not exist in the target month, Java adjusts it to the last day of that month. Thus, 2024-01-31 plus one month becomes 2024-02-29. For a non-leap year, 2023-01-31 plus one month becomes 2023-02-28:

```java
LocalDate january31 = LocalDate.of(2023, 1, 31);
System.out.println(january31.plusMonths(1)); // 2023-02-28
```

This is the API's date-adjustment rule, but it does not replace domain-specific business policies. If a billing cycle requires "the last day of every month", consider `YearMonth.atEndOfMonth()` or an explicitly defined end-of-month rule; do not assume every contract wants the default adjustment behavior.

## 4. Same Local Time Next Day: Use ZonedDateTime.plusDays

`ZonedDateTime` contains a date-time, a `ZoneId`, and the resolved offset. When the requirement is "still at 12:00 on the next calendar day in New York", perform the calendar calculation on `ZonedDateTime`:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime beforeDst = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, newYork);
ZonedDateTime tomorrowAtNoon = beforeDst.plusDays(1);

System.out.println(beforeDst);
// 2024-03-09T12:00-05:00[America/New_York]
System.out.println(tomorrowAtNoon);
// 2024-03-10T12:00-04:00[America/New_York]
System.out.println(Duration.between(
        beforeDst.toInstant(), tomorrowAtNoon.toInstant()).toHours());
// 23
```

This is an illustrative snippet to be placed inside a Java method. New York starts DST on 2024-03-10, causing the offset to change from `-05:00` to `-04:00`. `plusDays(1)` preserves noon on the next day according to the local calendar, even though the two noon instants are only 23 actual hours apart.

This approach fits meetings, appointments, local reminders, and shifts scheduled by regional wall-clock time. For a time that falls directly into a non-existent or repeated DST window, you still need a policy to handle gaps/overlaps; calendar arithmetic does not automatically determine whether the business wants to reject or adjust the time.

## 5. Exactly 24 Hours Later: Use Duration or Instant

If the meaning is "exactly 24 hours from now", shift a point in time using `Duration`:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, newYork);
ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));

System.out.println(after24Hours);
// 2024-03-10T13:00-04:00[America/New_York]
```

Adding exactly 24 hours leads to 13:00 because the elapsed time span is the goal. When using `Instant`, the intent is even clearer:

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.parse("2024-03-09T17:00:00Z");
Instant after24Hours = start.plus(Duration.ofHours(24));

System.out.println(after24Hours); // 2024-03-10T17:00:00Z
System.out.println(Duration.between(start, after24Hours).toHours()); // 24
```

Use `Duration` for timeouts, retry delays, network latency, "exact 15-minute" breaks, or the elapsed time between two points. Do not use `Duration.ofDays(1)` when the intent is "tomorrow at the same local time"; do not use `Period.ofDays(1)` if the requirement strictly mandates 86,400 seconds.

## 6. Complete Runnable Java 17+ Example

Save as **`CalendarVsTimelineDemo.java`**:

```java
import java.time.*;

public class CalendarVsTimelineDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZonedDateTime beforeDst = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, newYork);

        ZonedDateTime sameLocalTimeTomorrow = beforeDst.plusDays(1);
        ZonedDateTime exactly24HoursLater =
                beforeDst.plus(Duration.ofHours(24));

        System.out.println("Start: " + beforeDst);
        System.out.println("Calendar + 1 day: " + sameLocalTimeTomorrow);
        System.out.println("Timeline + 24 hours: " + exactly24HoursLater);
        System.out.println("Calendar elapsed hours: "
                + Duration.between(beforeDst.toInstant(),
                                  sameLocalTimeTomorrow.toInstant()).toHours());
        System.out.println("Timeline elapsed hours: "
                + Duration.between(beforeDst.toInstant(),
                                  exactly24HoursLater.toInstant()).toHours());

        LocalDate endOfJanuary = LocalDate.of(2024, 1, 31);
        System.out.println("Plus one calendar month: "
                + endOfJanuary.plusMonths(1));
        System.out.println("Period of one month: "
                + endOfJanuary.plus(Period.ofMonths(1)));

        Instant start = Instant.parse("2024-03-09T17:00:00Z");
        System.out.println("Instant + 24h: "
                + start.plus(Duration.ofHours(24)));
    }
}
```

Compile and run:

```bash
javac CalendarVsTimelineDemo.java
java CalendarVsTimelineDemo
```

**stdout** verified with Java 17:

```text
Start: 2024-03-09T12:00-05:00[America/New_York]
Calendar + 1 day: 2024-03-10T12:00-04:00[America/New_York]
Timeline + 24 hours: 2024-03-10T13:00-04:00[America/New_York]
Calendar elapsed hours: 23
Timeline elapsed hours: 24
Plus one calendar month: 2024-02-29
Period of one month: 2024-02-29
Instant + 24h: 2024-03-10T17:00:00Z
```

The output shows:
1. `plusDays(1)` preserves the local noon time on the next day; the elapsed duration is 23 hours.
2. `plus(Duration.ofHours(24))` adds exactly 24 hours, so the local time becomes 13:00.
3. January 31 plus one month is adjusted to the last day of February.
4. `Instant` + 24 hours preserves the exact span along the timeline.

## 7. Do Not Apply Duration Calculations When Handling Calendar Dates

A `LocalDate` has no time of day or zone. Therefore, `LocalDate.plusDays(1)` is a valid calendar-date calculation, whereas adding "86,400 seconds" requires assuming that a date can be represented as an actual point on the timeline. If the requirement is "next holiday", "next birthday", or "next billing date", use the calendar API and the corresponding business rules.

A `LocalDateTime` also has no zone. It allows adding calendar date/time fields, but it is not sufficient to determine exact elapsed duration without knowing the offset/zone. To measure the time difference between two locations, you must first convert each timestamp to an `Instant` with the proper zone/offset.

A `ZonedDateTime` has a geographic zone, so it can perform both calendar calculations and duration calculations. The difference lies in the type of the added amount: `plusDays(1)` is a calendar unit, while `plus(Duration.ofHours(24))` is a fixed duration.

## 8. Real-World Scenarios and How to Choose

| Requirement | Correct Interpretation |
| --- | --- |
| "Remind at 09:00 tomorrow in Hanoi" | Tomorrow's calendar date + `LocalTime` 09:00 + Vietnam `ZoneId`; resolve against the zone when scheduling the reminder |
| "Expire exactly 24 hours after order creation" | `createdAt.plus(Duration.ofHours(24))` |
| "Bill after one month" | Specify one calendar month and how to handle month-end, using `Period` or month arithmetic |
| "Same time tomorrow in New York" | `ZonedDateTime.plusDays(1)` and check DST if needed |
| "Retry after 30 seconds" | `Duration.ofSeconds(30)` |
| "Measure time between send and receive" | Two `Instant`s then `Duration.between(start, end)` |
| "Last day of the month" | `YearMonth.atEndOfMonth()` or a specific end-of-month rule |
| "After 365 days" | Add exactly 365 days as requested; do not implicitly treat it as one calendar year |
| "Same calendar date and time next month" | `LocalDate.plusMonths(1)` or `ZonedDateTime.plusMonths(1)` with an end-of-month policy |
| "Shift 22:00–06:00 next morning" | Determine start/end dates and zone; compute elapsed duration from the two resolved instants |

A field named `expiresAt` usually refers to an absolute point in time; `dueDate` may be a calendar date; `openTime` usually indicates opening hours. Confirm the semantics from the business requirements before choosing the type or addition operation.

## 9. DST, Month-End, and Boundaries

**DST:** a local day can be 23 or 25 actual hours long. Calendar calculations and duration calculations can yield different local times.

**Month-end:** months have 28, 29, 30, or 31 days. Java clamps the day if the source day does not exist in the target month; month-end business logic may require its own rules.

**Leap years:** `Duration.ofDays(365)` is not one calendar year. If the requirement is the next year, use calendar arithmetic on `LocalDate` or `ZonedDateTime` and clarify the policy for February 29.

**Midnight:** the same `Instant` can fall on different calendar dates depending on the zone. Convert to the business zone before extracting `LocalDate` to group reports or determine expiration dates.

**Repeated/skipped hours:** a `LocalDateTime` may not exist or may occur twice in a DST zone. When converting a local time to an actual instant, inspect `ZoneRules.getValidOffsets(local)` and decide whether to reject, adjust, or select an offset according to the agreed policy.

## 10. Common Mistakes

1. **Using `Duration.ofDays(1)` for "same time tomorrow".** It adds 24 elapsed hours and can shift the local time across DST.
2. **Using `Period.ofDays(1)` for a 24-hour timeout.** `Period` is a calendar unit; `Duration` is a fixed span.
3. **Treating a month as 30 days.** Month lengths vary; use calendar calculations.
4. **Treating a year as 365 days.** Leap years make this rule wrong for calendar years.
5. **Adding a `Duration` to a `LocalDateTime` and treating the result as an `Instant`.** `LocalDateTime` lacks a zone/offset; it does not identify an absolute point in time.
6. **Measuring the difference between two local times in different zones.** Convert to `Instant` first, then use `Duration.between`.
7. **Ignoring DST gaps/overlaps.** Local times may not exist or may occur twice; schedules need an explicit policy.
8. **Treating `plusMonths(1)` as adding a fixed number of seconds.** It is a calendar calculation and may clamp the day at month-end.
9. **Using the server's default time.** For zone-dependent or "today" logic, pass `ZoneId` explicitly and use `Clock` when deterministic testing is needed.
10. **Failing to define what "one day" means.** Clarify whether it means "the next calendar day" or "86,400 seconds" in the business contract.

## 11. Required Tests

| Test Case | Expected |
| --- | --- |
| New York 12:00 on 2024-03-09 plus one calendar day | 12:00 on 2024-03-10, elapsed duration 23 hours |
| Same timestamp plus 24 hours | 13:00 on 2024-03-10, elapsed duration 24 hours |
| 2024-01-31 plus one month | 2024-02-29 |
| Add one day in a zone without DST changes | Verify both the local value and the `Instant` |
| Schedule during a DST gap | Apply policy: reject or perform documented adjustment |
| Schedule during a DST overlap | Select/record one of the two offsets if a single `Instant` is required |
| Measure two events | Compare two `Instant`s and use `Duration.between` |
| Timeout | Verify total seconds and duration limit |

In JUnit 5, you can assert both results using `assertEquals` on `ZonedDateTime` or `Instant`, and verify that `Duration.between(start.toInstant(), end.toInstant()).toHours()` equals 23 or 24 in DST cases. When testing, comparing both the **local time** and the **actual instant** helps clarify the intent of the calculation.

## 12. Quick API Reference

| Goal | API |
| --- | --- |
| Next calendar day | `LocalDate.plusDays(1)` |
| Next calendar month | `LocalDate.plusMonths(1)` / `Period.ofMonths(1)` |
| Same local time tomorrow in a zone | `ZonedDateTime.plusDays(1)` |
| Add exactly one 24-hour day | `Instant.plus(Duration.ofDays(1))` |
| Fixed timeout | `Duration.ofSeconds/Minutes/Hours(...)` |
| Duration between two points | `Duration.between(Instant, Instant)` |
| End of month | `YearMonth.atEndOfMonth()` |
| Convert an instant to a display zone | `Instant.atZone(zone)` |
| Check local time in DST | `ZoneRules.getValidOffsets(local)` |

**Remember:** Use `Period` and calendar calculations for years/months/days; use `Duration` and `Instant` for fixed durations. When preserving local time in a zone, use `ZonedDateTime` and `ZoneId`. Before writing a calculation, clearly state whether the requirement needs to preserve a **calendar date/time** or shift by **an elapsed number of seconds**.
