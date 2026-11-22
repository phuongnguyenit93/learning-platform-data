# YearMonth for Reporting Periods and Monthly Due Dates

## 1. When a Month Is a Business Value

"Reporting period 02/2024" does not specify a day of the month, a time of day, or a time zone. Using `LocalDate.of(2024, 2, 1)` to represent the period can mislead readers into thinking the 1st has its own business meaning, when it is only a representative day chosen by the author.

`YearMonth` directly models the combination of **year and month**. According to the [Java API for YearMonth](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/YearMonth.html), this type uses the ISO calendar and does not contain a day-of-month, time, or time zone.

```java
YearMonth period = YearMonth.of(2024, 2);
```

The value `2024-02` is suitable for representing a sample revenue aggregation period, a service usage month, a planning month, or a due month. When a specific date is needed, we add a policy to convert from `YearMonth` to `LocalDate`.

| Information to represent | Appropriate type |
| --- | --- |
| February in general, without a year | `Month` |
| Month 02/2024 | `YearMonth` |
| Date 29/02/2024 | `LocalDate` |
| A specific point on the timeline | `Instant` |
| Date and time tied to a zone | `ZonedDateTime` |

`YearMonth` is immutable: `plusMonths` returns a new value. It is not a `LocalDate` with the day hidden, nor does it inherently represent the start or end of the month.

## 2. Creating, Reading, and Navigating Between Periods

Common ways, assuming the corresponding classes are imported:

```java
YearMonth explicit = YearMonth.of(2024, 2);
YearMonth parsed = YearMonth.parse("2024-02");
YearMonth fromDate = YearMonth.from(LocalDate.of(2024, 2, 29));

int year = explicit.getYear();
int monthNumber = explicit.getMonthValue();

YearMonth next = explicit.plusMonths(1);
YearMonth previous = explicit.minusMonths(1);
YearMonth nextYear = explicit.plusYears(1);
```

The default format for `parse`/`toString` with common years is `uuuu-MM`, such as `2024-02`. The string `02/2024` requires a matching formatter, not the default format. A string containing only `02` also does not identify a period because it lacks a year.

To display it differently, you can format it while keeping `YearMonth` as the underlying data:

```java
DateTimeFormatter display = DateTimeFormatter.ofPattern("MM/uuuu");
String label = explicit.format(display); // 02/2024
```

This is an illustration using `DateTimeFormatter` from `java.time.format`. Display strings should not become the basis for calculations or chronological sorting. For example, lexicographical sorting of `MM/uuuu` labels prioritizes the month before the year, not the actual period order.

`plusMonths` handles year transitions correctly according to the calendar:

- `2023-12.plusMonths(1)` yields `2024-01`.
- `2024-01.minusMonths(1)` yields `2023-12`.
- `2024-02.plusMonths(12)` yields `2025-02`.

Do not increment `monthNumber++` manually and maintain branches for month 13 or month 0. Also do not add `30` days to simulate a month; month lengths vary.

## 3. Converting a Reporting Period into a Date Range

For a `period`, there are three useful boundaries:

```java
LocalDate firstDay = period.atDay(1);
LocalDate lastDay = period.atEndOfMonth();
LocalDate nextFirstDay = period.plusMonths(1).atDay(1);
```

For February 2024:

| Milestone | Value |
| --- | --- |
| First day of the month | `2024-02-01` |
| Last day of the month | `2024-02-29` |
| First day of the next month | `2024-03-01` |

### 3.1. Prefer Half-Open Intervals for Filtering Data

A contract that makes it easy to chain adjacent periods is:

**[first day of the month, first day of the next month)**

The start date is inclusive; the end date is exclusive. The membership condition:

```java
boolean inside = !date.isBefore(firstDay)
        && date.isBefore(nextFirstDay);
```

The range for 02/2024 includes 29/02 but excludes 01/03. The range for 03 starts at the exact point where 02 ends, so a day is never counted twice just because two periods share a boundary.

If the data truly only has `LocalDate`, a closed interval from the first day to `atEndOfMonth()` can also be used when the contract explicitly states both ends are inclusive. What matters is that variable names and filter operators are consistent; do not name a variable `toExclusive` and then use `<=`.

### 3.2. Do Not Construct the "Last Second of the Month"

For data with a time component, `23:59:59` does not cover every end-of-day value because of fractional seconds. Using `23:59:59.999` also couples logic to the millisecond precision of a specific storage mechanism.

An exclusive end boundary avoids having to find the last possible value before the next month:

```sql
WHERE occurred_at >= :fromInclusive
  AND occurred_at <  :toExclusive
```

This is an illustrative SQL condition with parameters; both parameters must have the type and temporal meaning appropriate for the actual column. `YearMonth` does not by itself decide whether they are local dates, local date-times, or UTC instants.

### 3.3. When Data Is Stored as Instant, Choose the Zone Before Creating Boundaries

A monthly reporting period based on an organization's local time must have a business `ZoneId`. Once the zone is chosen, you can create the two boundaries:

```java
Instant fromInclusive =
        period.atDay(1).atStartOfDay(businessZone).toInstant();
Instant toExclusive =
        period.plusMonths(1).atDay(1)
                .atStartOfDay(businessZone).toInstant();
```

This illustration assumes `period` is a `YearMonth` and `businessZone` is a defined `ZoneId`. [LocalDate.atStartOfDay(ZoneId)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId)) chooses the earliest valid time of day according to the zone rules; you should not assume every zone always has a valid 00:00 on every historical date.

Do not compute the end boundary by taking the start boundary and adding `30 * 24` hours. Months have different numbers of days; in zones with DST transitions, the number of elapsed hours between two calendar boundaries can also vary.

Zone selection must be consistent across the entire report. The server's time zone does not automatically become the business time zone just because the program happens to run on that machine.

## 4. Monthly Due Dates Need an Additional Day Policy

`YearMonth` only identifies the due month. To get a due date, you must answer: **what happens if the desired day does not exist in that month?**

Example with a nominal due day of 31:

| Policy | Month 02/2024 | Meaning |
| --- | --- | --- |
| Require exact day | Reject because day 31 does not exist | Caller must fix the input or choose another rule |
| Nominal day or month end if missing | `2024-02-29` | Keep the nominal day for other months |
| Always month end | `2024-02-29` | Do not use a nominal day; every month takes the last day |

The last two policies produce the same result when the nominal day is 31, but not always. If the nominal day is 30, then March under the second policy is 30/03, whereas "always month end" gives 31/03.

### 4.1. atDay() Validates the Exact Day, Does Not Fall Back to Month End

`isValidDay(day)` tells whether a day exists in this month. `atDay(day)` creates a `LocalDate` if valid and throws `DateTimeException` if invalid.

```java
YearMonth february = YearMonth.of(2024, 2);

boolean valid = february.isValidDay(30); // false
LocalDate end = february.atEndOfMonth(); // 2024-02-29
// february.atDay(30) will throw DateTimeException.
```

Do not confuse `atDay(31)` with a request to "just take the last day of the month." This method has a strict validation contract.

### 4.2. Falling Back to Month End Must Be Written as an Explicit Policy

If the policy chooses the nominal day or the last day when missing, the formula is:

```java
int actualDay = Math.min(nominalDay, targetMonth.lengthOfMonth());
LocalDate dueDate = targetMonth.atDay(actualDay);
```

You must validate that `nominalDay` is in `1..31` first. If you only use `Math.min` and receive `99`, the program will silently turn an invalid input into the last day of the month. If it receives `0` or a negative number, taking the minimum will not turn it into a valid day either.

`lengthOfMonth()` accounts for the year, so 02/2024 has 29 days, while 02/2023 has 28. Do not maintain a fixed month-length table and forget leap years.

If the policy is truly month-end, calling `targetMonth.atEndOfMonth()` directly expresses the intent more clearly than pretending there is always a nominal day of 31.

### 4.3. Calendar Dates and Business Days Are Two Separate Layers

The last day of a month may fall on a weekend or a company holiday. `YearMonth` does not contain a holiday calendar and does not know whether a due date should be shifted earlier or later.

A clear design can consist of:

1. From the period and day rule, derive the **calendar due date**.
2. Apply a business-day policy if the business requires it.
3. Apply a cutoff time and time zone if a due instant is needed.

Do not silently add a day-shifting rule just because a date is a holiday. Shifting into a new month can affect the original month of the due date; keep the business period and the adjusted due date separate.

## 5. Avoiding Due Date Drift When Adding Months Sequentially

Consider a recurring schedule intended to be due on the 31st of each month, falling back to month end when missing:

```java
LocalDate january31 = LocalDate.of(2024, 1, 31);
LocalDate february29 = january31.plusMonths(1);
LocalDate march29 = february29.plusMonths(1);
```

The final result is 29/03. When adding from 29/02, the object no longer has the information that "the original nominal day was 31." It only knows the current day is 29.

Meanwhile:

```java
LocalDate march31 = january31.plusMonths(2);
```

gives 31/03. Direct addition and adding one month twice can differ due to day clamping in the intermediate month.

For a recurring schedule to preserve its intended rule, store separately:

- The anchor period, such as `YearMonth.of(2024, 1)`.
- The nominal day, such as `31`.
- The policy when the day is missing.
- The period index to compute.

For each period, compute `targetMonth = firstMonth.plusMonths(index)` and reapply the nominal-day policy. Do not use the shortened due date of the previous period as the sole source for the next period.

| Period | Keep nominal day 31 | Add sequentially from previous result |
| --- | --- | --- |
| 01/2024 | 31/01 | 31/01 |
| 02/2024 | 29/02 | 29/02 |
| 03/2024 | 31/03 | 29/03 |

This is a business-modeling decision, not a bug in `LocalDate.plusMonths`. That method processes its current input accurately; it cannot remember a recurring rule that was never stored.

## 6. Complete Java 17+ Program

Save as `YearMonthPeriodDemo.java`:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class YearMonthPeriodDemo {
    record DateRange(LocalDate fromInclusive, LocalDate toExclusive) {
        DateRange {
            Objects.requireNonNull(fromInclusive);
            Objects.requireNonNull(toExclusive);
            if (toExclusive.isBefore(fromInclusive)) {
                throw new IllegalArgumentException("Reversed range");
            }
        }

        boolean contains(LocalDate date) {
            Objects.requireNonNull(date);
            return !date.isBefore(fromInclusive)
                    && date.isBefore(toExclusive);
        }
    }

    static DateRange reportingRange(YearMonth period) {
        Objects.requireNonNull(period);
        return new DateRange(
                period.atDay(1),
                period.plusMonths(1).atDay(1));
    }

    static LocalDate dueOnDayOrMonthEnd(
            YearMonth targetMonth, int nominalDay) {
        Objects.requireNonNull(targetMonth);
        if (nominalDay < 1 || nominalDay > 31) {
            throw new IllegalArgumentException("Day must be 1..31");
        }
        return targetMonth.atDay(
                Math.min(nominalDay, targetMonth.lengthOfMonth()));
    }

    public static void main(String[] args) {
        YearMonth february = YearMonth.parse("2024-02");
        DateRange range = reportingRange(february);
        System.out.println("period = " + february);
        System.out.println("length = " + february.lengthOfMonth());
        System.out.println("start = " + range.fromInclusive());
        System.out.println("end exclusive = " + range.toExclusive());
        System.out.println("month end = " + february.atEndOfMonth());
        System.out.println("contains leap day = "
                + range.contains(LocalDate.of(2024, 2, 29)));
        System.out.println("contains next month = "
                + range.contains(LocalDate.of(2024, 3, 1)));
        System.out.println("valid day 30 = " + february.isValidDay(30));

        try {
            february.atDay(30);
        } catch (DateTimeException ex) {
            System.out.println("strict day -> "
                    + ex.getClass().getSimpleName());
        }

        YearMonth first = YearMonth.of(2024, 1);
        for (int index = 0; index < 3; index++) {
            YearMonth target = first.plusMonths(index);
            System.out.println("anchored " + target + " = "
                    + dueOnDayOrMonthEnd(target, 31));
        }

        LocalDate january31 = first.atDay(31);
        LocalDate sequential = january31.plusMonths(1).plusMonths(1);
        LocalDate direct = january31.plusMonths(2);
        System.out.println("sequential date = " + sequential);
        System.out.println("direct date = " + direct);

        YearMonth from = YearMonth.of(2023, 12);
        YearMonth to = YearMonth.of(2024, 3);
        System.out.println("month distance = "
                + ChronoUnit.MONTHS.between(from, to));
        for (YearMonth cursor = from;
                cursor.isBefore(to);
                cursor = cursor.plusMonths(1)) {
            System.out.println("report = " + cursor);
        }

        Clock fixed = Clock.fixed(
                Instant.parse("2024-02-29T23:30:00Z"),
                ZoneOffset.UTC);
        System.out.println("current UTC period = " + YearMonth.now(fixed));
        System.out.println("current business period = " + YearMonth.now(
                fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh"))));
        System.out.println("unchanged period = " + february);
    }
}
```

Compile and run:

```shell
javac --release 17 YearMonthPeriodDemo.java
java YearMonthPeriodDemo
```

Stdout:

```text
period = 2024-02
length = 29
start = 2024-02-01
end exclusive = 2024-03-01
month end = 2024-02-29
contains leap day = true
contains next month = false
valid day 30 = false
strict day -> DateTimeException
anchored 2024-01 = 2024-01-31
anchored 2024-02 = 2024-02-29
anchored 2024-03 = 2024-03-31
sequential date = 2024-03-29
direct date = 2024-03-31
month distance = 3
report = 2023-12
report = 2024-01
report = 2024-02
current UTC period = 2024-02
current business period = 2024-03
unchanged period = 2024-02
```

`DateRange` in the example represents a half-open interval over `LocalDate`, allowing equal endpoints to represent an empty range while rejecting reversed ranges. `reportingRange` always produces a complete month.

`dueOnDayOrMonthEnd` is named to reflect the fall-back-to-month-end policy. It does not accept an adjusted date from the previous period, so the due-date loop returns to 31/03 instead of sticking at 29/03.

The `unchanged period` line shows that operations do not mutate `february`. To advance a loop variable, you must reassign the result: `cursor = cursor.plusMonths(1)`.

## 7. Iterating Periods and Measuring Distance in Months

Count the number of periods from 12/2023 up to (before) 03/2024:

```java
long count = ChronoUnit.MONTHS.between(
        YearMonth.of(2023, 12),
        YearMonth.of(2024, 3)); // 3
```

The three corresponding periods are 12/2023, 01/2024, and 02/2024. If you want to include 03 as well, that is a different contract; for ascending monthly period ranges, you can convert an inclusive end to an exclusive end using `endInclusive.plusMonths(1)` when still within the representable domain.

When the end is before the start, `between` can return a negative number. An API that only accepts ascending ranges should validate and reject reversed inputs rather than using `Math.abs` to silently flip the meaning of the request.

A `YearMonth` loop is suitable for:

- Generating a complete list of periods in a chart, including periods with no data yet.
- Initializing statistics buckets with `0` for missing months.
- Computing recurring due dates from an anchor period.
- Bounding a report by a defined sequence of months.

Do not iterate day by day and discard non-1st days just to build a list of months. Both the model and the iteration step should operate at the month unit.

If you put `YearMonth` into a `Map` or a set, use `equals` for value comparison; do not use `==`. `YearMonth` has a natural chronological order via `compareTo`, `isBefore`, and `isAfter`.

## 8. "Current Month" Depends on the Clock and Time Zone

The value `YearMonth.of(2024, 2)` has no time zone of its own. However, to answer "what month is it now?", the program must obtain a current instant and interpret it in a zone.

`YearMonth.now()` uses the system default clock and time zone. This may not match the zone of the organization using the system. `YearMonth.now(zone)` explicitly selects the zone; `YearMonth.now(clock)` also allows controlling the clock for testing.

The example in the program fixes the instant `2024-02-29T23:30:00Z`:

- In UTC, it is still 02/2024.
- In `Asia/Ho_Chi_Minh` in the example, it is already the morning of 01/03/2024, so the current period is 03/2024.

The two results do not contradict each other because they use two local interpretations of the same instant.

For historical reports, pass the specific period into the function instead of having the function call `now()` itself. If a job is re-run after crossing into a new month, the period to process must still match the original request, not change based on the rerun date.

Similarly, if a multi-step workflow needs the same "current period," determine the period once at the start of the workflow and pass it down. Do not re-read the clock at each step right near a month boundary.

## 9. Separating Period, Due Date, and Expiration Instant

The following three values are not interchangeable:

| Value | Example | Additional info needed to determine an instant |
| --- | --- | --- |
| Period | `2024-02` | Day, time, and zone rules |
| Due date | `2024-02-29` | Cutoff time, zone, and date-inclusivity convention |
| Exclusive expiration instant | A specific `Instant` | Already has a point on the timeline |

If the rule allows usage through the end of the due date in the local calendar, one way to model it is to take the start of the next day as the exclusive end boundary. However, this is only valid when that is the chosen policy; a 17:00 deadline cannot share that rule.

Keeping `YearMonth` as the period key ensures that adjusting a due date to the first day of the next month does not lose its association with the original period. For example, the February service period remains `2024-02` even if a business rule moves the processing date to early March.

When exchanging data, the standard string `2024-02` is a compact representation for common periods. The data access layer must still configure conversions appropriate for the technology in use; Java does not automatically guarantee that every serializer or every database has a native `YearMonth` type.

If a system stores a period as the first day of the month or as a pair of year/month columns, document clearly that this is a storage representation and enforce constraints. Avoid letting a synthetic representative date be misused as an actual transaction date or due date.

## 10. Limits and Common Pitfalls

`YearMonth` has a finite year range according to the API. For example, creating a reporting range for the very last month in the domain by adding one month will overflow the range. Applications typically use a narrower year range; validate inputs against the supported range instead of assuming every addition will succeed.

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using a month number `1..12` as a period key | Mixes data across multiple years | Use year and month together |
| Using `LocalDate` on day 01 without stating it is a representative date | Confuses the period with an actual date | Model the period with `YearMonth` |
| Adding 30 days to move to the next month | Period drift | Use `plusMonths` |
| Calling `atDay(31)` expecting it to pick month end | Exception on short months | Use `atEndOfMonth` or a clearly named policy |
| Taking `min` without validating the nominal day | Input 99 can be masked as month end | Validate `1..31` first |
| Adding months from the previous period's adjusted due date | Due date drifts over time | Compute each period from the original nominal day |
| Using the "last second of the month" as the end boundary | Misses data with fractional seconds | Use the start of the next month exclusively |
| Using server time to determine the business period | Wrong month near boundaries | Specify the zone and clock explicitly |
| Failing to reassign the result of `plusMonths` | Loop variable never changes | Assign the new result |
| Treating month end as always equal to 30 days or a fixed number of hours | Wrong interval length | Build boundaries from the calendar and zone |

## 11. Self-Check and Practice

1. Create ranges for 02/2023 and 02/2024. Check `lengthOfMonth`, `atEndOfMonth`, and the first day of the next month.
2. Test `contains` with the day right before the period, the first day of the period, the last day of the period, and the first day of the next period. Only the two cases inside the period should be accepted.
3. Generate due dates for nominal day 30 from 01 to 03/2024. The results should be 30/01, 29/02, 30/03; compare with the always-month-end policy.
4. Generate due dates for nominal day 31 in 2023. Month 02 uses 28/02, and month 03 must return to 31/03 when using the described policy.
5. Test nominal days `0`, `32`, and `99`. The function must report invalid input rather than silently fixing it into a seemingly valid date.
6. Iterate from 11/2023 up to (before) 02/2024. It must generate exactly three periods and handle the year transition naturally.
7. Use a `Clock.fixed` near a month boundary to test period selection in UTC and in a business zone. No need to wait for the real clock to roll over to the next month.
8. Write a function that takes a period and a zone and returns two `Instant`s as month boundaries. Verify that data exactly at the start boundary is included and data exactly at the end boundary is excluded.
9. Suppose a due date falling on a holiday must be moved to the preceding business day. Describe where to apply the business-day policy without changing how the monthly period is identified.
10. Explain why a reporting period, a due date, and an expiration instant should be stored or passed using types with distinct meanings.

The key takeaway is that `YearMonth` identifies the period; a day policy determines the calendar due date; and time-of-day and time-zone rules determine a point on the timeline. When each step has its own contract, handling short months, leap years, and period boundaries becomes consistent.
