# Week-Based Year at the Year-End Boundary in Java

## 1. The Problem: January 1 Can Belong to the Previous "Week Year"

In reporting systems, work calendars, or scheduling tools, you may see a date in calendar year 2021 labeled as **week 53 of 2020**. This is not a date calculation bug:

- Calendar date **2021-01-01** has `YEAR = 2021`.
- Under **ISO 8601 weeks**, that date belongs to **2020-W53**, i.e., week 53 of **week-based-year 2020**.
- Similarly, **2018-12-31** is in calendar year 2018, yet under **ISO** it is in **2019-W01**.

This discrepancy arises because the **week-based-year** is determined by whole weeks or the first week of the year under calendar rules, which does not align strictly with January 1 through December 31.

Java provides `LocalDate`, `WeekFields`, `IsoFields`, and `DateTimeFormatter` to compute and format week-based dates. In Java Core localization, you must clearly distinguish **ISO rules** from **locale week rules** and avoid the common mistake of using `YYYY` instead of `yyyy` or `uuuu`.

## 2. Distinguishing Three Concepts: Calendar Year, Week of Year, and Week-Based Year

| Concept | Typical Java API | Meaning |
| --- | --- | --- |
| Calendar year | `LocalDate.getYear()`, `ChronoField.YEAR`, pattern `uuuu` | Year containing that date in the proleptic ISO/Gregorian calendar |
| Week of calendar year | `WeekFields.weekOfYear()` | Counts weeks **within the calendar year**, can include **week 0**; do not use to build ISO week codes |
| Week-based year | `WeekFields.weekBasedYear()` | The year that "owns" the week; can differ from calendar year at the start/end of the year |
| Week of week-based year | `WeekFields.weekOfWeekBasedYear()` | Week number, typically 1–52 or 1–53 within the week-based year |
| Day of week | `DayOfWeek`, `WeekFields.dayOfWeek()` | Day in ISO ordering or localized ordering |

**Never combine** `date.getYear()` with `date.get(WeekFields.ISO.weekOfWeekBasedYear())` and treat the result as an ISO week code. Late December sometimes belongs to the next week-based year, and early January days can belong to the previous week-based year. The correct pair must be:

```java
WeekFields iso = WeekFields.ISO;
int weekYear = date.get(iso.weekBasedYear());
int week = date.get(iso.weekOfWeekBasedYear());
```

This is a snippet; `date` is an already constructed `LocalDate` and requires `import java.time.temporal.WeekFields;`. Both fields rely on **one consistent week definition**.

### Why does week-of-year differ from week-of-week-based-year?

`weekOfYear()` counts within calendar year boundaries, so the beginning of a year without enough days for week 1 can be numbered **week 0**, and a week can be split across New Year's Eve. By contrast, `weekOfWeekBasedYear()` counts the weeks of a *week-based-year*: every complete week belongs to exactly one week-based year, so days spilling into an adjacent calendar year are assigned to week 1 or week 52/53 of a single week-based year.

If the goal is a standard week code like `2020-W53`, use **week-based-year + week-of-week-based-year**, not year + week-of-year.

## 3. ISO 8601 Rules for Week-Based Year

Under ISO 8601:

1. **Weeks start on Monday**.
2. **Week 1 is the week with at least four days in the new calendar year**. Equivalently, the week containing **January 4**, or the week containing the **first Thursday of the year**.
3. A week-based year has **52 or 53 weeks**.
4. A week is never split across New Year's Eve: the final week can end in January of the next year, or the first week can begin in December of the previous year.

Java represents this rule with:

```java
WeekFields iso = WeekFields.ISO;
System.out.println(iso.getFirstDayOfWeek());       // MONDAY
System.out.println(iso.getMinimalDaysInFirstWeek()); // 4
```

This is a snippet inside a Java method, with `import java.time.temporal.WeekFields;`.

For example, calendar year 2021 started on a Friday. The week from Monday 2020-12-28 to Sunday 2021-01-03 has **four days in 2020** and only **three days in 2021**, so it is **week 53 of week-based year 2020**. Week 1 of week-based year 2021 begins on Monday 2021-01-04.

### Table of boundary dates under ISO

| Calendar Date | Calendar Year | ISO Week-Based Year | ISO Week | ISO Day of Week |
| --- | ---: | ---: | ---: | --- |
| `2014-12-29` | 2014 | 2015 | 01 | Monday (1) |
| `2018-12-31` | 2018 | 2019 | 01 | Monday (1) |
| `2020-12-27` | 2020 | 2020 | 52 | Sunday (7) |
| `2020-12-31` | 2020 | 2020 | 53 | Thursday (4) |
| `2021-01-01` | 2021 | 2020 | 53 | Friday (5) |
| `2021-01-03` | 2021 | 2020 | 53 | Sunday (7) |
| `2021-01-04` | 2021 | 2021 | 01 | Monday (1) |

The rows `2014-12-29` and `2018-12-31` show the reverse case: a date in **late December** already belongs to **the next week-based year**.

**Warning:** week 53 does not exist in every week-based year. You cannot assume the final week is always 52, nor can you increment week 52 to 53 by simple addition; rely on calendar algorithms or standard APIs.

## 4. WeekFields.ISO vs. Locale-Based WeekFields

Not every country or region follows the ISO rule. Some systems take **Sunday** as the first day of the week and require only **one day** in the new year for week 1. Java supports these rules:

```java
WeekFields iso = WeekFields.ISO;
WeekFields us = WeekFields.of(Locale.US);
WeekFields custom = WeekFields.of(DayOfWeek.SUNDAY, 1);
```

In the common configuration of `Locale.US`, `us` and `custom` share the same rule: weeks start on Sunday, with at least one day in the year to count as week 1. Under that rule, the week starting **2020-12-27** is assigned to **week 1 of week-based year 2021** because it contains January 1, 2021.

| Date | ISO (Monday, min=4) | US (Sunday, min=1) |
| --- | --- | --- |
| `2020-12-27` | `2020-W52` | `2021-W01` |
| `2020-12-31` | `2020-W53` | `2021-W01` |
| `2021-01-01` | `2020-W53` | `2021-W01` |
| `2021-01-03` | `2020-W53` | `2021-W02` |
| `2021-01-04` | `2021-W01` | `2021-W02` |

**Locale only specifies week partitioning/display formatting in this context; it does not shift instants or time zones.** When weeks are used for ISO-standard international reporting, specify `WeekFields.ISO` even if the UI language is US English. When business logic requires a company or region-specific calendar week, define `firstDayOfWeek` and `minimalDaysInFirstWeek` explicitly.

### WeekFields.of(locale) is not an ISO contract

`WeekFields.of(Locale)` retrieves local week conventions from the runtime's locale data. Do not rely on "which locale sounds European" to conclude it is always ISO in every deployment. If the data standard is ISO 8601, **use `WeekFields.ISO` or `IsoFields` explicitly**. If company rules apply, **use `WeekFields.of(firstDay, minimalDays)`** with verified values.

`WeekFields` is immutable and thread-safe; the same instance can be reused. Its returned fields are `TemporalField` objects, readable via `LocalDate.get(...)`.

## 5. Runnable Java 17+ Example: Years and Weeks Table at Year Boundaries

Create the file **`WeekBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.List;
import java.util.Locale;

public class WeekBoundaryDemo {
    private static String yearWeek(LocalDate date, WeekFields rules) {
        int year = date.get(rules.weekBasedYear());
        int week = date.get(rules.weekOfWeekBasedYear());
        return String.format(Locale.ROOT, "%04d-W%02d", year, week);
    }

    public static void main(String[] args) {
        List<LocalDate> dates = List.of(
                LocalDate.of(2014, 12, 29),
                LocalDate.of(2018, 12, 31),
                LocalDate.of(2020, 12, 27),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2021, 1, 3),
                LocalDate.of(2021, 1, 4)
        );

        WeekFields iso = WeekFields.ISO;
        WeekFields us = WeekFields.of(Locale.US);

        for (LocalDate date : dates) {
            System.out.println(date
                    + " | calendar=" + date.getYear()
                    + " | ISO=" + yearWeek(date, iso)
                    + " | US=" + yearWeek(date, us));
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 WeekBoundaryDemo.java
java WeekBoundaryDemo
```

**Output under ISO and US rules (US week rules as in modern JDKs):**

```text
2014-12-29 | calendar=2014 | ISO=2015-W01 | US=2015-W01
2018-12-31 | calendar=2018 | ISO=2019-W01 | US=2019-W01
2020-12-27 | calendar=2020 | ISO=2020-W52 | US=2021-W01
2020-12-31 | calendar=2020 | ISO=2020-W53 | US=2021-W01
2021-01-01 | calendar=2021 | ISO=2020-W53 | US=2021-W01
2021-01-03 | calendar=2021 | ISO=2020-W53 | US=2021-W02
2021-01-04 | calendar=2021 | ISO=2021-W01 | US=2021-W02
```

Explanation:

1. `date.getYear()` is strictly the calendar year. It remains **2021** on 2021-01-01.
2. `yearWeek(date, iso)` reads both `weekBasedYear()` and `weekOfWeekBasedYear()` from **the same `WeekFields.ISO`**, printing `2020-W53` on 2021-01-01.
3. `yearWeek(date, us)` uses Sunday-start and minimum 1 day; therefore 2020-12-27 is already in `2021-W01`.
4. `String.format(Locale.ROOT, "%04d-W%02d", ...)` only left-pads zeroes for the report label. It **does not compute weeks**; both temporal fields were fetched from the Java API beforehand.
5. The ISO week outputs are normative; `Locale.US` week conventions should be treated as localized data verified in the runtime environment whenever they affect business contracts.

This example can be used to test 52/53-week years, December/January boundaries, and how week rules vary by locale.

## 6. Easy-to-Hit Bug: YYYY Differs from yyyy and uuuu

In `DateTimeFormatter.ofPattern(...)`:

| Symbol | Field | Meaning |
| --- | --- | --- |
| `Y`, `YYYY` | Week-based-year (localized) | Week-based year; can differ from calendar year |
| `w`, `ww` | Week of week-based-year | Week number within the week-based year |
| `W` | Week of month (localized) | Week within the month, **not** week of year |
| `e`, `ee` | Localized day-of-week | Day number per the locale's first day of week |
| `E`, `EEE`, `EEEE` | Day-of-week name | Uses day name instead of day number |
| `y`, `yyyy` | Year-of-era | Year within an era (for CE, typically matches calendar year) |
| `u`, `uuuu` | Proleptic year | Continuous calendar year, including year 0 and negative years in ISO |
| `M` | Month of year | Month of year |
| `d` | Day of month | Day of month |

A classic bug:

```java
LocalDate date = LocalDate.of(2020, 12, 31);

DateTimeFormatter calendar = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US);
DateTimeFormatter dangerous = DateTimeFormatter
        .ofPattern("YYYY-MM-dd", Locale.US);

System.out.println(date.format(calendar));  // 2020-12-31
System.out.println(date.format(dangerous)); // 2021-12-31
```

This is a **snippet**: requires `import java.time.LocalDate;`, `java.time.format.DateTimeFormatter;`, and `java.util.Locale;`. With US week rules, month/day remain 12/31 while `YYYY` belongs to **week-based year 2021**, producing a string that **looks like December 31, 2021 even though the underlying data is December 31, 2020**. That is why **you should never use `YYYY-MM-dd` merely to print a calendar date**.

If you want a year-month-day calendar date, prefer `DateTimeFormatter.ISO_LOCAL_DATE` or `uuuu-MM-dd`. For ordinary CE dates, `yyyy-MM-dd` usually prints the same year too, but `yyyy` is year-of-era and behaves differently from `uuuu` for BC/year 0 or strict parsing.

### Why is YYYY not necessarily the ISO week-based-year?

In `DateTimeFormatter`, `Y`, `w`, and `e` are localized according to the formatter's `Locale`. On the same date:

```java
LocalDate date = LocalDate.of(2020, 12, 31);

System.out.println(date.format(
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.US)));
System.out.println(date.format(
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.UK)));
```

Output with JDK 24 locale data:

```text
2021-W01-5
2020-W53-4
```

In this example:
- `Locale.US` takes Sunday as the first day of the week, so Thursday is day **5** of the week and the week-based year is already **2021**.
- `Locale.UK` applies ISO-like rules, so Thursday is day **4**, belonging to **2020-W53**.

**Do not assume "`YYYY` always equals ISO week-based-year".** If the goal is ISO, use `DateTimeFormatter.ISO_WEEK_DATE` or `WeekFields.ISO`; if the goal is local weeks, explicitly specify the locale and rules matching the product.

## 7. Using DateTimeFormatter.ISO_WEEK_DATE to Exchange ISO Weeks

Java provides a built-in formatter for ISO week dates:

```java
DateTimeFormatter.ISO_WEEK_DATE
```

Example:

```java
LocalDate date = LocalDate.of(2021, 1, 1);
String weekDate = date.format(DateTimeFormatter.ISO_WEEK_DATE);
// "2020-W53-5"

LocalDate parsed = LocalDate.parse(
        "2020-W53-5", DateTimeFormatter.ISO_WEEK_DATE);
// 2021-01-01
```

Components of `2020-W53-5`:

- `2020` — **week-based-year**, not the calendar year of the date.
- `W53` — week 53 of the week-based year.
- `5` — Friday under ISO (Monday = 1, Sunday = 7).

Unlike strings containing only `2020-W53`, `ISO_WEEK_DATE` includes the **day of the week** to uniquely identify a single `LocalDate`. If you only store week-year + week-number for a reporting calendar, that represents **a week span**, not a specific day. To find the start of the week, set the ISO day to Monday using the appropriate temporal API.

### Standalone example: safe round-trip for ISO weeks

Create the file **`IsoWeekDateDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class IsoWeekDateDemo {
    public static void main(String[] args) {
        LocalDate source = LocalDate.of(2021, 1, 1);
        String encoded = source.format(DateTimeFormatter.ISO_WEEK_DATE);
        LocalDate decoded = LocalDate.parse(
                encoded, DateTimeFormatter.ISO_WEEK_DATE);

        System.out.println("Date: " + source);
        System.out.println("ISO week date: " + encoded);
        System.out.println("Decoded: " + decoded);
        System.out.println("Same date: " + source.equals(decoded));

        try {
            LocalDate.parse("2021-W53-1", DateTimeFormatter.ISO_WEEK_DATE);
        } catch (DateTimeParseException e) {
            System.out.println("Invalid week: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 IsoWeekDateDemo.java
java IsoWeekDateDemo
```

Stdout:

```text
Date: 2021-01-01
ISO week date: 2020-W53-5
Decoded: 2021-01-01
Same date: true
Invalid week: DateTimeParseException
```

The example also tests the case where **week-based year 2021 has no ISO week 53**. `ISO_WEEK_DATE` applies standard rules with a strict resolver; never treat `2021-W53-1` as a valid date. For user-entered strings, catch the parse error and surface an appropriate message rather than silently clamping week 53 down to week 52.

## 8. WeekFields and IsoFields: Choosing the Right Tool

Alongside `WeekFields.ISO`, Java offers `java.time.temporal.IsoFields`:

```java
import java.time.LocalDate;
import java.time.temporal.IsoFields;

LocalDate d = LocalDate.of(2021, 1, 1);

int year = d.get(IsoFields.WEEK_BASED_YEAR); // 2020
int week = d.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR); // 53
```

Differences:

| API | Characteristics | When to Use |
| --- | --- | --- |
| `WeekFields.ISO` | Preconfigured ISO WeekFields with year/week/day fields | When you want a full set of ISO week fields |
| `WeekFields.of(locale)` | First day of week and minimal days per locale | Local calendars / UI |
| `WeekFields.of(firstDay, minDays)` | Explicit custom week rule | Business / enterprise calendars |
| `IsoFields.WEEK_BASED_YEAR` | ISO week-based-year field | Logic strictly using ISO |
| `IsoFields.WEEK_OF_WEEK_BASED_YEAR` | ISO week-number field | Logic strictly using ISO |
| `DateTimeFormatter.ISO_WEEK_DATE` | ISO week-date formatter/parser | Exchanging `yyyy-Www-d` in the **week-based-year** sense, including day of week |

`IsoFields` never picks `Locale.US` rules and is a clear way to express **ISO**. `WeekFields.ISO.weekBasedYear()` and `IsoFields.WEEK_BASED_YEAR` return the same value for ISO `LocalDate`, though you should never mix fields from **different week rules** in the same week code.

**Note on `yyyy` in documentation**: when describing an ISO week date, the year group means **week-based-year**; in **Java patterns**, `yyyy` means **year-of-era**. Avoid ambiguous descriptions like "yyyy-Www"; better to write a concrete example `2020-W53-5` and use `DateTimeFormatter.ISO_WEEK_DATE`.

## 9. Rules for Week 53

Under ISO, most week-based years have 52 weeks, while some have 53. Intuitively:

- A common year has 365 days = 52 weeks + 1 day.
- A leap year has 366 days = 52 weeks + 2 days.
- Because ISO weeks start on Monday and week 1 requires at least four days in the year, when the extra days and weekday alignment line up, week 53 appears.

A commonly used rule: **a common calendar year starting on Thursday, or a leap year starting on Wednesday**, will have **53 ISO weeks**. For instance, leap year 2020 started on Wednesday, so `2020-W53` exists. Year 2021 started on Friday, so it has only 52 ISO weeks.

However, **do not hardcode** week counts using manual formulas in applications spanning multiple years, calendars, or local week rules. You can use Java to check the week of December 28: under ISO, **December 28 always falls in the final week of the week-based year corresponding to that calendar year**.

```java
LocalDate lastWeekAnchor = LocalDate.of(2020, 12, 28);
int lastIsoWeek = lastWeekAnchor.get(
        WeekFields.ISO.weekOfWeekBasedYear()); // 53
```

This is a snippet with `import java.time.LocalDate;`, `java.time.temporal.WeekFields;`. It is a simple trick to check 52/53 ISO weeks, not a universal rule for every local week system.

## 10. Real-World Bugs in Reports, Logging, and Identifiers

### 10.1. Using YYYY for calendar dates

A `"YYYY-MM-dd"` formatter can print a different year in December or early January; the date string is off by one year even though `LocalDate` is correct. If that string is stored as a data key, the bug can propagate to search, reconciliation, or scheduling.

**Fix:** use `DateTimeFormatter.ISO_LOCAL_DATE`/`"uuuu-MM-dd"` for dates, and use week-based-year only when genuinely expressing weeks.

### 10.2. Building week codes from calendar year and ISO week

Incorrect example:

```java
int wrongYear = date.getYear();
int isoWeek = date.get(WeekFields.ISO.weekOfWeekBasedYear());
// combining wrongYear + "-W" + isoWeek is wrong at boundary dates.
```

For 2021-01-01, the code above produces **2021-W53**, an ISO week that **does not exist**. The correct approach is reading `WeekFields.ISO.weekBasedYear()` for the year portion.

### 10.3. Specifying "weeks start on Monday" while forgetting minimalDays

Knowing only that weeks start on Monday is **not enough** to determine the week-based year. If minimal days is 1 instead of 4, end-of-year and start-of-year weeks receive different labels. Any weekly reporting contract must state both **the first day of the week** and **the minimal days in the first week**.

### 10.4. Confusing local weeks with ISO

If accounting closes on ISO weeks while a dashboard uses `WeekFields.of(Locale.US)`, an event on 2020-12-31 can be bucketed into a different week/year. Never let the dashboard viewer's locale dictate accounting period rules unless the product intentionally permits it.

### 10.5. Confusing week-of-month with week-of-week-based-year

Uppercase `W` (week of month) differs from lowercase `w` (week of week-based year), and `Y` differs from `y`. A single case error changes **data semantics**, not merely formatting style.

### 10.6. Storing "W53" without a week-based year

The label week 53 does not identify which year's week it is. Store at least the **week-based-year + week** pair, and if a specific day is needed add **day-of-week**, or store the week's start/end dates under a defined policy.

### 10.7. Using current LocalDateTime without specifying a time zone

Week-based dates are computed from **calendar dates**. The same `Instant` can be December 31 in one time zone and already January 1 in another. When grouping events by week, first determine the **business `ZoneId`**, convert the `Instant` to a `LocalDate` in that zone, and only then compute the week-based year. `Locale` does not determine the time zone.

### 10.8. Relying solely on New Year's Eve for full testing

Testing only `12-31` is insufficient. Test `12-29` through `12-31`, `01-01` through `01-04`, and special years with ISO week 53. Bugs occur on both sides of the year boundary.

## 11. Testing Boundaries and Invariants

A solid test suite should include:

| Test Case | Expected ISO Result |
| --- | --- |
| `2014-12-29` | `2015-W01` |
| `2018-12-31` | `2019-W01` |
| `2020-12-31` | `2020-W53` |
| `2021-01-01` | `2020-W53` |
| `2021-01-03` | `2020-W53` |
| `2021-01-04` | `2021-W01` |
| `2021-12-31` | Week 52 of week-based year 2021 |
| `2020-W53-5` via ISO_WEEK_DATE | Parses to `2021-01-01` |
| `2021-W53-1` via ISO_WEEK_DATE | Throws `DateTimeParseException` |

Beyond the standard case table, you can test **invariants** across an entire date range:

1. For each date, compute `year = get(weekBasedYear())` and `week = get(weekOfWeekBasedYear())` from the same `WeekFields.ISO`.
2. `week` must be within `1..53`.
3. Two dates 7 days apart on the same day of the week have consecutive ISO week codes (possibly advancing to a new week-based year).
4. For every date, `date.format(DateTimeFormatter.ISO_WEEK_DATE)` followed by `LocalDate.parse(..., ISO_WEEK_DATE)` must return the exact original date.
5. For applications using localized weeks, re-run the test suite whenever the locale/provider or business week rule changes.

When testing against real timestamps, fix the **time zone** before deriving `LocalDate`. When comparing output strings, fix both the week rule and formatting pattern rather than relying on the JVM default locale.

## 12. Review Questions

**Q1.** Why does `LocalDate.of(2021, 1, 1)` have calendar year 2021 yet ISO week `2020-W53`?

**Answer:** ISO weeks start on Monday, and week 1 must have at least four days in the new year. The week 2020-12-28 through 2021-01-03 has only three days in 2021, so it belongs to week-based year 2020.

**Q2.** Is `DateTimeFormatter.ofPattern("YYYY-MM-dd")` the right way to store Gregorian dates?

**Answer:** No. `Y` is the week-based year, which can change earlier or later than the calendar year. Use `DateTimeFormatter.ISO_LOCAL_DATE` or `"uuuu-MM-dd"`.

**Q3.** A system requires ISO weeks; should it use `WeekFields.of(Locale.US)`?

**Answer:** No. `WeekFields.of(Locale.US)` uses local week definitions, typically Sunday-start with min 1. Use `WeekFields.ISO` or `IsoFields` when data must follow ISO.

**Q4.** How do you parse an ISO date from `"2020-W53-5"`?

**Answer:** `LocalDate.parse(value, DateTimeFormatter.ISO_WEEK_DATE)`. The result is `2021-01-01`.

**Q5.** Why is `2021-W53-1` an invalid ISO code?

**Answer:** Week-based year 2021 has only 52 ISO weeks; `ISO_WEEK_DATE` with a strict resolver rejects strings specifying week 53.

**Q6.** When reporting weekly totals only, does the data need the day of the week?

**Answer:** If each row represents a **week span**, the `week-based-year + week` pair suffices to identify that span once a single week rule is agreed upon. If a specific day must be identified, include the day of week or calendar date.

**Q7.** The same event is viewed in Tokyo and New York and falls on different dates. Which date determines the week-based year?

**Answer:** Follow the **defined business time zone** (such as the user's time zone, event venue time zone, or UTC per contract). Convert the `Instant` to a `LocalDate` in that zone before computing the week; never pick arbitrarily from locale.

## 13. Takeaways

- **Calendar year** and **week-based year** are two distinct numbering systems at year boundaries. `2021-01-01` is **2020-W53** under ISO.
- ISO 8601 defines **Monday** as the start of the week and **at least 4 days** of the year in week 1.
- In Java, read **both** `WeekFields.ISO.weekBasedYear()` and `WeekFields.ISO.weekOfWeekBasedYear()` together to construct ISO week codes.
- `Y`/`YYYY` is the **localized week-based-year**, different from `y` and `u`. Never use `"YYYY-MM-dd"` for calendar dates.
- `WeekFields.of(Locale)` can differ from `WeekFields.ISO`. Analysis, storage, and reporting must agree on **week rules and time zones**.
- `DateTimeFormatter.ISO_WEEK_DATE` is the clear choice for formatting/parsing **ISO week dates**, including the day of the week.

Official references:

- [Java SE 21 — WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)
- [Java SE 21 — IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html)
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [ISO 8601 — Date and time representations](https://www.iso.org/iso-8601-date-and-time-format.html)
