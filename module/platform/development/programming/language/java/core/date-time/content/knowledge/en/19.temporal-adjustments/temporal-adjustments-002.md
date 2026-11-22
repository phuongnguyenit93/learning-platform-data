# First Day of Month, Last Day of Month, First Day of Year, and Last Day of Year

## Determining Calendar Period Boundaries Instead of Counting Days Manually

A report needs to know which dates the month containing `2024-02-18` starts and ends on. If you manually add 30 days or assume the last day is always 31, the result will be wrong in many months.

`java.time` provides temporal adjusters to directly express requirements such as "the first day of the month" or "the last day of the year". With `LocalDate`, you receive an adjusted date value; the source date is not modified.

In this lesson, months and years refer to ISO calendar periods: standard calendar months and years from January 1 to December 31. Fiscal years, last business days of the month, or custom company closing periods follow different rules.

## 1. The Four Basic Adjustments

Use `date.with(adjuster)` together with the methods in `TemporalAdjusters`:

| Requirement | How to write |
| --- | --- |
| First day of the month containing `date` | `date.with(TemporalAdjusters.firstDayOfMonth())` |
| Last day of the month containing `date` | `date.with(TemporalAdjusters.lastDayOfMonth())` |
| First day of the year containing `date` | `date.with(TemporalAdjusters.firstDayOfYear())` |
| Last day of the year containing `date` | `date.with(TemporalAdjusters.lastDayOfYear())` |

These adjustments compute boundaries based on the period containing the input date itself, not the machine's current month or year. [`TemporalAdjusters` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)

With `date = 2024-02-18`:

```text
Month 02/2024:
2024-02-01 ───────── 2024-02-18 ───────── 2024-02-29
first of month       source date          last of month

Year 2024:
2024-01-01 ───────── 2024-02-18 ───────── 2024-12-31
first of year        source date          last of year
```

This is an adjustment by position within the calendar, which differs from "adding one month" or "adding 30 days". Setting a date to the end of the month does not mean always adding the same number of days.

## 2. Complete Program

Save as `CalendarBoundariesDemo.java`. The program uses Java 17 or later and the standard library:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;

public class CalendarBoundariesDemo {
    private static boolean contains(
            LocalDate startInclusive,
            LocalDate endExclusive,
            LocalDate candidate) {
        return !candidate.isBefore(startInclusive)
                && candidate.isBefore(endExclusive);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 18);

        LocalDate monthStart =
                date.with(TemporalAdjusters.firstDayOfMonth());
        LocalDate monthEnd =
                date.with(TemporalAdjusters.lastDayOfMonth());
        LocalDate yearStart =
                date.with(TemporalAdjusters.firstDayOfYear());
        LocalDate yearEnd =
                date.with(TemporalAdjusters.lastDayOfYear());

        LocalDate nextMonthStart =
                date.with(TemporalAdjusters.firstDayOfNextMonth());
        LocalDate nextYearStart =
                date.with(TemporalAdjusters.firstDayOfNextYear());

        System.out.println("original=" + date);
        System.out.println("monthStart=" + monthStart);
        System.out.println("monthEnd=" + monthEnd);
        System.out.println("yearStart=" + yearStart);
        System.out.println("yearEnd=" + yearEnd);
        System.out.println("nextMonthStart=" + nextMonthStart);
        System.out.println("nextYearStart=" + nextYearStart);

        System.out.println("normalFebruaryEnd="
                + LocalDate.of(2023, 2, 10)
                        .with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("century1900End="
                + LocalDate.of(1900, 2, 10)
                        .with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("century2000End="
                + LocalDate.of(2000, 2, 10)
                        .with(TemporalAdjusters.lastDayOfMonth()));

        YearMonth month = YearMonth.from(date);
        System.out.println("yearMonthStart=" + month.atDay(1));
        System.out.println("yearMonthEnd=" + month.atEndOfMonth());

        System.out.println("monthDayCount="
                + ChronoUnit.DAYS.between(monthStart, nextMonthStart));
        System.out.println("yearDayCount="
                + ChronoUnit.DAYS.between(yearStart, nextYearStart));

        System.out.println("containsLastDay="
                + contains(monthStart, nextMonthStart, monthEnd));
        System.out.println("containsNextMonth="
                + contains(monthStart, nextMonthStart, nextMonthStart));

        LocalDate marchReference = LocalDate.of(2024, 3, 18);
        LocalDate marchStart =
                marchReference.with(TemporalAdjusters.firstDayOfMonth());
        LocalDate aprilStart =
                marchReference.with(TemporalAdjusters.firstDayOfNextMonth());

        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime start = marchStart.atStartOfDay(paris);
        ZonedDateTime end = aprilStart.atStartOfDay(paris);

        System.out.println("parisStart=" + start);
        System.out.println("parisEnd=" + end);
        System.out.println("parisElapsedHours="
                + Duration.between(start.toInstant(), end.toInstant()).toHours());
    }
}
```

Compile and run:

```shell
javac --release 17 CalendarBoundariesDemo.java
java CalendarBoundariesDemo
```

Stdout with time-zone data containing the 2024 rules used in the example:

```text
original=2024-02-18
monthStart=2024-02-01
monthEnd=2024-02-29
yearStart=2024-01-01
yearEnd=2024-12-31
nextMonthStart=2024-03-01
nextYearStart=2025-01-01
normalFebruaryEnd=2023-02-28
century1900End=1900-02-28
century2000End=2000-02-29
yearMonthStart=2024-02-01
yearMonthEnd=2024-02-29
monthDayCount=29
yearDayCount=366
containsLastDay=true
containsNextMonth=false
parisStart=2024-03-01T00:00+01:00[Europe/Paris]
parisEnd=2024-04-01T00:00+02:00[Europe/Paris]
parisElapsedHours=743
```

The program uses fixed dates so that the results can be verified independently of the run date.

## 3. End of Month Depends on Both Month and Year

A month can have 28, 29, 30, or 31 days. The year directly affects February. The test lines in the program show:

- February 2023 ends on the 28th.
- February 2024 ends on the 29th.
- February 1900 ends on the 28th.
- February 2000 ends on the 29th.

Therefore, a fixed table saying "February has 28 days", or a simple rule that only checks divisibility by 4, does not fully replace the ISO leap-year rules.

When using `lastDayOfMonth()`, the library retrieves the day limit appropriate for the month and year of the value being adjusted. You do not need to write extra branches for each month. [Last day of month documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#lastDayOfMonth())

Similarly, the last day of an ISO year is always December 31, but its position within the year can be day 365 or 366. Computing the number of days in a year from two consecutive start-of-year boundaries covers that difference.

## 4. Writing with Direct Fields or `YearMonth`

With `LocalDate`, you can use:

```java
LocalDate firstDate = date.withDayOfMonth(1);
LocalDate lastDate = date.withDayOfMonth(date.lengthOfMonth());

LocalDate firstDateOfYear = date.withDayOfYear(1);
LocalDate lastDateOfYear = date.withDayOfYear(date.lengthOfYear());
```

This is an illustrative snippet using an existing `date` variable. These forms specify the field to replace directly; named adjusters are often easier to read when you want to express a calendar rule. Choose one consistent and clear style in your code—there is no need to write both to do the same job.

If the input is already a monthly period, keep `YearMonth`:

```java
YearMonth reportingMonth = YearMonth.of(2024, 2);
LocalDate startDate = reportingMonth.atDay(1);
LocalDate endDateInclusive = reportingMonth.atEndOfMonth();
```

`YearMonth` does not hold a day, time, or time zone. `atDay(1)` creates the first day of the month; `atEndOfMonth()` creates the last day appropriate for the year and month. [`YearMonth` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/YearMonth.html)

This approach avoids creating an arbitrary mid-month date just to find the month boundaries afterward. The full program also demonstrates that the results from `YearMonth` match the boundaries found from the source date.

## 5. Distinguishing "Last Day" from "Exclusive End Bound"

These two quantities are related but different:

```text
Last day of month 02/2024:
    2024-02-29

Interval representing the entire month:
    [2024-02-01, 2024-03-01)
```

The `[` bracket means the start bound is inclusive; the `)` parenthesis means the end bound is exclusive.

When you need to display the last day so the reader sees the calendar date, use `lastDayOfMonth()`. When you need to filter data belonging to the entire month, using the start of the next month as the exclusive end bound is usually clearer:

```java
LocalDate startInclusive =
        date.with(TemporalAdjusters.firstDayOfMonth());
LocalDate endExclusive =
        date.with(TemporalAdjusters.firstDayOfNextMonth());

boolean inMonth = !candidate.isBefore(startInclusive)
        && candidate.isBefore(endExclusive);
```

This is an illustrative snippet, assuming `date` and `candidate` are `LocalDate`.

The corresponding rule for a year:

```java
LocalDate startInclusive =
        date.with(TemporalAdjusters.firstDayOfYear());
LocalDate endExclusive =
        date.with(TemporalAdjusters.firstDayOfNextYear());
```

For December, the end bound automatically advances to January 1 of the next year. There is no need to manually reset the month, day, and year with multiple branches.

Two adjacent monthly intervals can share a boundary without overlapping:

```text
Month 02: [2024-02-01, 2024-03-01)
Month 03: [2024-03-01, 2024-04-01)
```

Do not name a variable generically as `endDate` if it could be confused as inclusive versus exclusive. Names like `endDateInclusive` and `endExclusive` help callers use the right comparison.

## 6. When Data Represents Instants, a Time Zone Is Needed to Define the Period

`LocalDate` only represents a date; it has no time of day or time zone. A date-based "first of the month" does not by itself define an `Instant`.

If you need to filter events by month in a specific region:

1. Determine the date boundaries in that region's calendar.
2. Convert each boundary using `atStartOfDay(zone)`.
3. Use the resulting `Instant` values as the inclusive start bound and exclusive end bound.

The program illustrates March 2024 in Paris:

```text
Start of month:      2024-03-01 00:00 +01:00
Start of next month: 2024-04-01 00:00 +02:00
Calendar days:       31 days
Elapsed hours:       743 hours
```

This month has an offset transition, so the total hours are not `31 * 24`. Calendar period boundaries must be computed by calendar and zone; do not replace them with a fixed number of seconds.

`atStartOfDay(zone)` chooses the earliest valid time of the day according to the zone's rules. In some time-zone transition cases, that time is not necessarily `00:00`. [`LocalDate.atStartOfDay` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId))

Also distinguish the following:

```java
// Illustrative snippet: adjusts the date but does not automatically set the time to start of day.
ZonedDateTime changedDate =
        originalZoned.with(TemporalAdjusters.firstDayOfMonth());
```

If `originalZoned` has an afternoon time, adjusting the date is not a request for "first of the month at the start of the day". To get an instant boundary of the month, express both intentions as shown in the steps above.

Do not construct an end bound as "last day at 23:59:59" and assume it includes all data. Data can have fractional seconds and different precisions. An interval up to the start of the next period avoids relying on choosing a "last instant" before the boundary.

## 7. Common Pitfalls

### Forgetting to capture the return value

`LocalDate` is immutable. The following does not change the `date` variable:

```java
date.with(TemporalAdjusters.firstDayOfMonth());
```

Save the result when you need to use it:

```java
LocalDate firstDate =
        date.with(TemporalAdjusters.firstDayOfMonth());
```

Do not rely on whether an adjustment creates a different object or returns a reusable one; what matters is the return value.

### Adding one month and subtracting one day from an arbitrary date

```java
LocalDate mistaken = date.plusMonths(1).minusDays(1);
```

This does not generally mean the last day of the month containing `date`. If `date` is in the middle of the month, the result is usually also in the middle of the next month.

If you use the "first day of next month minus one day" approach, you must first determine the start of the month or use the proper adjuster:

```java
LocalDate lastDate =
        date.with(TemporalAdjusters.firstDayOfNextMonth()).minusDays(1);
```

Using `lastDayOfMonth()` directly usually states the intent more clearly.

### Using day 31 for every month

`withDayOfMonth(31)` is not a way to request the last valid day. It can throw an exception in months that do not have a 31st day. Use the month's length or the corresponding adjuster.

### Confusing calendar periods with business periods

`lastDayOfMonth()` can be a Saturday or Sunday. It does not mean "the last business day of the month". Similarly, `firstDayOfYear()` does not automatically know that a fiscal year starts in April.

If you have a custom holiday calendar or fiscal period, you need additional rules and appropriate data; do not change the meaning of existing API names.

## 8. Choosing the Source Date and Verifying Boundaries

If a report needs the user's current month, determine the reference zone and read the current date once, for example:

```java
ZoneId reportingZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate referenceDate = LocalDate.now(reportingZone);
```

Then compute all boundaries from `referenceDate`. Do not call `now()` multiple times to compute each boundary separately, because execution could cross a day, month, or year rollover. In tests, pass a fixed source date or a controllable clock.

Useful test cases:

- A mid-month date and dates already at the start or end of the month.
- Months with 30 and 31 days.
- February in leap years and non-leap years.
- December when creating the start bound of the next month.
- December 31 when creating the start bound of the next year.
- A calendar period in a zone with an offset transition if the result is used as an instant interval.

An input that is already the first or last day of a period should yield the same corresponding **boundary value**. Verify with `equals`, not reference comparison with `==`.

## 9. Self-Practice

1. From `2024-02-18`, which method gets the last day of the month without manually checking for leap years?
2. To filter the entire month of February 2024 as a half-open interval, what is the end bound date?
3. Why is `plusMonths(1).minusDays(1)` from an arbitrary date not guaranteed to be the end of the month?
4. Is the first day of the month on a `LocalDate` automatically a UTC instant?
5. Does `lastDayOfMonth()` guarantee the result is a business day?

Suggested answers:

1. `date.with(TemporalAdjusters.lastDayOfMonth())`.
2. `2024-03-01`, exclusive.
3. Because the date has not been anchored to a boundary; addition preserves the relationship to the source date.
4. No; you need a zone or offset and a rule for choosing the time of day.
5. No; it is the last calendar day, not a business calendar day.

Use named adjusters to find date boundaries, clearly distinguish the last day from an exclusive end bound, and only convert to instants after the applicable time zone has been determined.
