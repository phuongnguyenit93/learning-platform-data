# Do Not Convert Months and Years to Fixed Numbers of Seconds in Java

## 1. Problem and Goal

Months and years are **calendar units**, not fixed-length amounts of time. A month can be 28, 29, 30, or 31 days long; a common year has 365 days and a leap year has 366 days. In time zones with DST, a local day can even be 23 or 25 hours of elapsed time.

In Java, separate the two semantics:

- `java.time.Period` represents a calendar amount in years, months, and days.
- `java.time.Duration` represents an amount of time in seconds and nanoseconds.
- `java.time.LocalDate` and `LocalDateTime` represent calendar fields; they do not contain a time zone on their own.
- `java.time.Instant` is an absolute point in time; `ZoneId` and `ZonedDateTime` apply regional time rules.

"Renew for one month" is a calendar requirement. "Wait exactly 720 hours" is a duration requirement. You should not replace these two concepts with the same constant number of seconds.

## 2. Why Is There No Fixed Number of Seconds for a Month or a Year?

| Calendar Unit | Number of Days | Seconds (assuming 86,400 seconds per day) |
| --- | ---: | ---: |
| February (common year) | 28 | 2,419,200 |
| February (leap year) | 29 | 2,505,600 |
| 30-day month | 30 | 2,592,000 |
| 31-day month | 31 | 2,678,400 |
| Common year | 365 | 31,536,000 |
| Leap year | 366 | 31,622,400 |

The numbers in the table only convert a **specific number of days** to seconds; they do not prove that a month or a year has a universal length. For example, 30 × 24 × 60 × 60 equals 2,592,000 seconds, but that is exactly 30 days, not necessarily one calendar month.

Moreover, 86,400 seconds is a 24-hour day in terms of duration. In a region with DST, a local calendar day can have only 23 hours or 25 hours. Therefore, do not use constant multiplication to represent months/years or calendar days in all contexts.

## 3. Differences Between Period and Duration

| Criterion | Period | Duration |
| --- | --- | --- |
| Components | Years, months, days | Seconds, nanoseconds |
| Semantics | Calendar span | Elapsed time |
| Example | `Period.ofMonths(1)` | `Duration.ofDays(30)` |
| Suitable for | Contract terms, anniversaries, calendar cycles | Timeouts, execution time, difference between two instants |

```java
Period month = Period.ofMonths(1);
Duration thirtyDays = Duration.ofDays(30);

System.out.println(month);       // P1M
System.out.println(thirtyDays);  // PT720H
```

This is an illustrative snippet inside a method; it requires importing `java.time.Period` and `java.time.Duration`. `P1M` is one calendar month; `PT720H` is 720 hours. A `Period` does not contain a start date, so on its own it does not have a fixed total number of seconds.

## 4. Adding One Calendar Month

Use `LocalDate.plusMonths(1)` or `plus(Period.ofMonths(1))` when you want to advance by one calendar month.

```java
LocalDate leapStart = LocalDate.of(2024, 1, 31);
LocalDate ordinaryStart = LocalDate.of(2023, 1, 31);

System.out.println(leapStart.plusMonths(1));     // 2024-02-29
System.out.println(ordinaryStart.plusMonths(1)); // 2023-02-28
```

This illustrative code requires importing `java.time.LocalDate`. If the 31st does not exist in the target month, Java adjusts to the last valid day of that month. February 2024 has 29 days because 2024 is a leap year; February 2023 has 28 days.

Complete program **CalendarMonthDemo.java**:

```java
import java.time.LocalDate;
import java.time.Period;

public class CalendarMonthDemo {
    public static void main(String[] args) {
        LocalDate leapStart = LocalDate.of(2024, 1, 31);
        LocalDate ordinaryStart = LocalDate.of(2023, 1, 31);

        System.out.println("leapYear = "
                + leapStart.plus(Period.ofMonths(1)));
        System.out.println("ordinaryYear = "
                + ordinaryStart.plus(Period.ofMonths(1)));
        System.out.println("daysInFeb2024 = "
                + LocalDate.of(2024, 2, 1).lengthOfMonth());
        System.out.println("daysInFeb2023 = "
                + LocalDate.of(2023, 2, 1).lengthOfMonth());
    }
}
```

Compile and run with Java 17+:

```bash
javac CalendarMonthDemo.java
java CalendarMonthDemo
```

Output:

```text
leapYear = 2024-02-29
ordinaryYear = 2023-02-28
daysInFeb2024 = 29
daysInFeb2023 = 28
```

## 5. Adding One Calendar Year

```java
LocalDate leapDay = LocalDate.of(2024, 2, 29);
System.out.println(leapDay.plusYears(1)); // 2025-02-28
```

This illustrative code requires importing `java.time.LocalDate`. February 29 does not exist in 2025, so it is adjusted to February 28. If an anniversary business rule requires treating February 29 as March 1 instead of February 28, you must write a custom rule.

Similarly, `LocalDateTime.plusYears(1)` adjusts the date part according to calendar rules but does not add a time zone. `LocalDateTime` is not sufficient to determine an instant without knowing the source offset or `ZoneId`.

## 6. One Month Is Not the Same as 30 Days

```java
LocalDate start = LocalDate.of(2024, 2, 1);

System.out.println(start.plus(Period.ofMonths(1))); // 2024-03-01
System.out.println(start.plusDays(30));             // 2024-03-02
```

This illustrative code requires `LocalDate` and `Period`. Because February 2024 has 29 days, adding one month moves February 1 to March 1; adding exactly 30 days moves it to March 2.

| Start Date | +1 Calendar Month | +30 Days |
| --- | --- | --- |
| 2024-02-01 | 2024-03-01 | 2024-03-02 |
| 2024-04-01 | 2024-05-01 | 2024-05-01 |
| 2024-01-31 | 2024-02-29 | 2024-03-01 |

The two calculations can coincidentally produce the same result for a given start date, but they are not generally equivalent. Read the requirements carefully before choosing an operation: "one month later" is different from "after 30 days".

## 7. Period Consists of Years, Months, and Days

```java
Period contract = Period.of(1, 2, 3);
System.out.println(contract); // P1Y2M3D

LocalDate start = LocalDate.of(2024, 1, 31);
System.out.println(start.plus(contract));
```

This illustrative snippet requires `Period` and `LocalDate`. A `Period` holds calendar components, not a total number of days. The end-of-month day may be adjusted when applying a `Period` to a start date.

`Period.getDays()` only returns the days component, not the total number of days between two dates. If you need the day difference between two `LocalDate` values, use `ChronoUnit.DAYS.between(start, end)`.

## 8. Duration Represents Fixed Elapsed Time

When the requirement is exactly 30 days of elapsed time, you can use `Duration`:

```java
Duration thirtyDays = Duration.ofDays(30);
Instant start = Instant.parse("2024-02-01T00:00:00Z");
Instant end = start.plus(thirtyDays);

System.out.println(thirtyDays); // PT720H
System.out.println(end);        // 2024-03-02T00:00:00Z
```

This illustrative code requires `java.time.Duration` and `java.time.Instant`. A `Duration` of 30 days is a fixed 720 hours in the elapsed-time model.

Choosing based on the requirement:

- Exactly 720 hours: `Duration.ofHours(720)`.
- Next calendar year: `plusYears(1)`.
- Next calendar month: `plusMonths(1)` or `Period.ofMonths(1)`.
- 15-minute timeout: `Duration.ofMinutes(15)`.
- One-month contract renewal: `Period`, along with a clearly defined end-of-month policy.

## 9. Calendar Days and DST

`Duration.ofDays(1)` is 24 hours. `ZonedDateTime.plusDays(1)` advances to the next calendar day in the zone and can be 23 or 25 hours from the initial instant when DST occurs.

Complete program **DstCalendarDayDemo.java**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstCalendarDayDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime start =
                LocalDate.of(2024, 3, 31).atStartOfDay(paris);
        ZonedDateTime nextDay = start.plusDays(1);
        ZonedDateTime after24Hours = start.plus(Duration.ofDays(1));

        System.out.println("start = " + start);
        System.out.println("calendarNextDay = " + nextDay);
        System.out.println("after24Hours = " + after24Hours);
        System.out.println("elapsedHours = "
                + Duration.between(start, nextDay).toHours());
    }
}
```

Compile and run:

```bash
javac DstCalendarDayDemo.java
java DstCalendarDayDemo
```

Output according to Paris rules on March 31, 2024:

```text
start = 2024-03-31T00:00+01:00[Europe/Paris]
calendarNextDay = 2024-04-01T00:00+02:00[Europe/Paris]
after24Hours = 2024-04-01T01:00+02:00[Europe/Paris]
elapsedHours = 23
```

From the start of March 31 to the start of April 1 in Paris, there are only 23 elapsed hours. Adding a 24-hour `Duration` lands at 01:00. When operating on local days, keep the `ZoneId` and use calendar operations; a fixed offset does not contain full DST rules.

## 10. Choosing the Right API for the Problem

| Question | API | Meaning |
| --- | --- | --- |
| How many calendar days between two dates? | `ChronoUnit.DAYS.between(a, b)` | Calendar day difference |
| Add one month? | `date.plusMonths(1)` | Moving on the calendar |
| Add exactly 90 minutes to an instant? | `instant.plus(Duration.ofMinutes(90))` | Shifting elapsed time |
| How many hours elapsed between two instants? | `Duration.between(a, b)` | Duration |
| Same time on the next calendar day? | `zoned.plusDays(1)` | Applying zone rules |
| Start of day in a zone? | `date.atStartOfDay(zone).toInstant()` | Calendar boundary to instant |

Do not use `Duration` for calendar months because `Duration` does not carry a month component. For two `LocalDate` values, calculate the day difference with `ChronoUnit.DAYS.between`; for two instants, use `Duration` to measure elapsed time.

## 11. Avoiding Expiration Code with Wrong Semantics

The following calculation creates a point 30 fixed days later:

```java
Instant expiry = created.plusSeconds(30L * 24 * 60 * 60);
```

It does not mean "one month later". If the creation date is 2024-01-31, adding 30 days can land on March 1, whereas adding one calendar month moves the date to February 29.

If the deadline is specified by calendar date and local time, you must define the date, time, and `ZoneId`:

```java
LocalDate dueDate = LocalDate.of(2024, 1, 31).plusMonths(1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime deadline = dueDate.atTime(23, 59).atZone(zone);
Instant deadlineInstant = deadline.toInstant();
```

This illustrative code requires `LocalDate`, `ZoneId`, `ZonedDateTime`, and `Instant`. Do not assume UTC when the requirement actually refers to local time.

## 12. Recurring Cycles and End-of-Month Dates

Repeatedly adding months starting from the 31st can change the anchor day after the first month:

```java
LocalDate date = LocalDate.of(2024, 1, 31);
date = date.plusMonths(1); // 2024-02-29
date = date.plusMonths(1); // 2024-03-29
```

If the business rule is the last day of the month, express that rule explicitly:

```java
LocalDate januaryEnd = LocalDate.of(2024, 1, 1)
        .with(TemporalAdjusters.lastDayOfMonth());
LocalDate februaryEnd = LocalDate.of(2024, 2, 1)
        .with(TemporalAdjusters.lastDayOfMonth());

System.out.println(januaryEnd);  // 2024-01-31
System.out.println(februaryEnd); // 2024-02-29
```

This code requires `import java.time.temporal.TemporalAdjusters;`. Billing schedules must clearly define rules for the 29th/30th/31st, February 29, weekends, and holidays. Do not assume simple month addition handles every policy.

## 13. Converting Period to Elapsed Time

Only when you have a start point and an appropriate calendar context can you calculate the concrete length of a `Period`.

```java
LocalDate start = LocalDate.of(2024, 2, 1);
LocalDate end = start.plus(Period.ofMonths(1));

System.out.println(end); // 2024-03-01
System.out.println(ChronoUnit.DAYS.between(start, end)); // 29
```

This illustrative snippet requires `LocalDate`, `Period`, and `ChronoUnit`. In this example, a specific month is 29 days long. A different start date can yield a different number of days.

If you need the duration between date-times in a zone, attach a `ZoneId` and then compute the difference between the two points:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime start = LocalDate.of(2024, 3, 1).atStartOfDay(paris);
ZonedDateTime end = start.plusMonths(1);
Duration elapsed = Duration.between(start, end);
System.out.println(elapsed.toHours());
```

This is an illustrative snippet with the corresponding imports. The total hours depend on the offset rules in that interval. There is no conversion from `Period` to seconds independent of the start date and time zone.

## 14. Common Mistakes

| Mistake | Why Is It Wrong? | Correct Approach |
| --- | --- | --- |
| One month = 30 days | Wrong for 28/29/31-day months | `Period.ofMonths(1)` or `plusMonths(1)` |
| One year = 365 days | Ignores leap years | `Period.ofYears(1)` or `plusYears(1)` |
| Using `Duration` for calendar months | Wrong semantics | Separate calendar from elapsed time |
| `Duration.ofDays(1)` is one local day | DST can make a day 23/25 hours | `ZonedDateTime.plusDays(1)` |
| Using `Period.getDays()` as total days | Only gets the days component | `ChronoUnit.DAYS.between(a, b)` |
| Repeatedly adding months from the 31st without a rule | The day can shrink to 29/30 | Define an end-of-month rule |
| Storing only `LocalDateTime` for an absolute point in time | Missing offset and `ZoneId` | Choose `Instant`/`OffsetDateTime`/`ZonedDateTime` |

## 15. Self-Check Exercises

**Question 1.** What date is `LocalDate.of(2024, 2, 1).plusMonths(1)`?

**Answer:** `2024-03-01`.

**Question 2.** Starting from 2024-02-01, what date is 30 days later?

**Answer:** `2024-03-02`.

**Question 3.** Is `Duration.ofDays(1)` always equivalent to `ZonedDateTime.plusDays(1)`?

**Answer:** No. `Duration` is a fixed 24 hours; a calendar day is affected by zone rules and DST.

**Question 4.** What date does `LocalDate.of(2024, 2, 29).plusYears(1)` produce?

**Answer:** `2025-02-28` according to Java's calendar adjustment rules.

**Question 5.** Why does `Period.ofMonths(1)` not have a fixed number of seconds?

**Answer:** The length depends on the start date and target month; in a zoned context, it also depends on time zone rules.

**Question 6.** Which API should you use to measure elapsed time between two `Instant` values?

**Answer:** `Duration.between(startInstant, endInstant)`.

**Question 7.** What should you use to advance to the next calendar day in Paris?

**Answer:** `ZonedDateTime.plusDays(1)` with `ZoneId` `Europe/Paris`.

**Key Takeaway:** Do not convert calendar months/years into fixed numbers of seconds. Use `Period` and calendar operations for months/years; use `Duration` for elapsed time. When time zones are involved, distinguish "next calendar day" from "after exactly N hours", especially around DST.