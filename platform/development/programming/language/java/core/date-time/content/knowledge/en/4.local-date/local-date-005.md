# Adding and Subtracting Days, Weeks, Months, and Years with LocalDate in Java

`LocalDate` in the `java.time` package represents an **ISO-8601 calendar date** consisting of a year, month, and day, such as `2024-02-29`. It is suitable for handling deadlines, appointment dates, anniversaries, billing periods, or transaction posting dates. Java provides direct addition and subtraction operations without needing to convert calendar dates into milliseconds.

**Key takeaway:** Adding/subtracting **days and weeks** follows the number of calendar days; adding/subtracting **months and years** must check whether the day exists in the target month/year. The methods always return a new `LocalDate` because this class is **immutable**. Month-end and leap-year edge cases need to be understood carefully, especially when calculating recurring periods.

## 1. What does LocalDate represent?

Example:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
~~~

This is an **illustrative code snippet**; you need to import `java.time.LocalDate` and place it inside an appropriate class/method. The value holds the date 2024-02-29 but **does not contain a time, offset, or time zone**. A calendar date is not a single `Instant` on the timeline.

The addition and subtraction operations below have **calendar** semantics, following ISO rules:

| Unit | Add | Subtract | Meaning |
|---|---|---|---|
| Day | `plusDays(n)` | `minusDays(n)` | Move forward or backward by `n` calendar days. |
| Week | `plusWeeks(n)` | `minusWeeks(n)` | Move forward or backward by `7 × n` calendar days. |
| Month | `plusMonths(n)` | `minusMonths(n)` | Change month/year, adjusting the day if the target month is shorter. |
| Year | `plusYears(n)` | `minusYears(n)` | Change year, adjusting 02-29 if needed. |

Each parameter `n` has type `long`. `plusDays(0)` keeps the date value unchanged; you can pass a negative number like `plusDays(-3)` to move back three days (equivalent to `minusDays(3)` within the valid range). When expressing intent, prefer `plus` for "after" and `minus` for "before".

Do not assume `LocalDate.plusDays(1)` means "exactly 24 real hours" after a point in time: the length of the interval between the start of two consecutive calendar days in some regions with DST transitions can differ from 24 hours. When you need to add an absolute duration, refer to `Instant`/`Duration` after establishing a zoned point in time.

## 2. Adding and subtracting days: crossing calendar boundaries automatically

`plusDays` and `minusDays` automatically handle the number of days in each month, leap years, and year transitions:

| Expression | Result |
|---|---|
| `LocalDate.of(2024, 2, 28).plusDays(1)` | `2024-02-29` |
| `LocalDate.of(2024, 2, 29).plusDays(1)` | `2024-03-01` |
| `LocalDate.of(2023, 2, 28).plusDays(1)` | `2023-03-01` |
| `LocalDate.of(2024, 1, 1).minusDays(1)` | `2023-12-31` |
| `LocalDate.of(2024, 12, 31).plusDays(1)` | `2025-01-01` |

There is no need to manually write logic like "if February then add days using 28 or 29". `LocalDate` uses the ISO calendar system and knows the length of every month.

**Distinguish between the number of days added and inclusive counting at both ends.** For example, adding 5 days to `2024-05-01` reaches `2024-05-06`; however, if a user calls May 1 "day 1", then "day 5" is May 5. This is a business requirement choice, not a syntax difference.

Calendar date ranges should generally be represented as **half-open** `[from, until)` intervals so adjacent boundaries do not overlap. Starting on May 1 and ending before May 6 covers exactly five calendar days.

## 3. Adding and subtracting weeks: seven calendar days, not seven business days

One week in `LocalDate` arithmetic is seven days:

~~~text
2024-05-15 + 1 week  = 2024-05-22
2024-05-15 - 2 weeks = 2024-05-01
2024-12-29 + 1 week  = 2025-01-05
~~~

`plusWeeks(1)` preserves the day of the week. If the starting date is Wednesday, the result is Wednesday of the following week—it **does not automatically move to the start of the week on Monday**. To find the nearest Monday not after a given date, use `TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)`.

A week is also not "5 business days". Weekends and public holidays must be calculated according to organizational and regional calendars; `LocalDate` does not know holiday schedules on its own.

## 4. Adding and subtracting months: the end-of-month rule

Months have 28, 29, 30, or 31 days. When calling `plusMonths(n)` or `minusMonths(n)`, Java:

1. Computes the **target year and month** after shifting the months.
2. Keeps the **day-of-month** of the original date if the target month has that day.
3. If the target month does not have that day number, selects the **last valid day** of the target month.

Examples:

| Original date | Operation | Result | Explanation |
|---|---|---|---|
| `2023-01-31` | `plusMonths(1)` | `2023-02-28` | February 2023 has 28 days. |
| `2024-01-31` | `plusMonths(1)` | `2024-02-29` | February 2024 has 29 days. |
| `2024-03-31` | `minusMonths(1)` | `2024-02-29` | Moving back one month into February of a leap year. |
| `2024-05-31` | `plusMonths(1)` | `2024-06-30` | June only has 30 days. |
| `2024-12-31` | `plusMonths(2)` | `2025-02-28` | Crosses the new year and clamps the day. |
| `2024-08-30` | `minusMonths(6)` | `2024-02-29` | Day 30 does not exist in the target month. |

Conceptually, a single `plusMonths(n)` call performs:

~~~text
targetYearMonth = initial yearMonth + n months
targetDay       = min(originalDay, lengthOfMonth(targetYearMonth))
result          = day targetDay of targetYearMonth
~~~

This **clamp-to-end-of-month** rule applies to month addition/subtraction, not to every date-modifying method. For example, `LocalDate.of(2023, 2, 1).withDayOfMonth(31)` throws `DateTimeException` because February 31 is invalid.

**Do not replace `plusMonths(1)` with `plusDays(30)`:** January has 31 days, February has 28/29, and other months have 30/31 days. The two operations express different requirements.

## 5. Adding and subtracting years: watch out for February 29

`plusYears(n)` and `minusYears(n)` try to keep the month and day in the new year. If that date does not exist, the clamp-to-end-of-month rule applies, most notably for leap day:

~~~text
2024-02-29 + 1 year  = 2025-02-28
2024-02-29 - 1 year  = 2023-02-28
2024-02-29 + 4 years = 2028-02-29
2024-06-15 + 1 year  = 2025-06-15
~~~

In the proleptic ISO/Gregorian calendar, a leap year is divisible by 4, except years divisible by 100 that are not divisible by 400. Therefore, 2000 is a leap year, while 1900 and 2100 are not.

You can use `date.isLeapYear()`, `date.lengthOfMonth()`, and `date.lengthOfYear()` to check for leap years and get the appropriate day counts. "One calendar year" is not always 365 days, and "one calendar month" is not always 30 days.

**The February 29 anniversary rule is a business policy.** Java chooses `02-28` when adding one year to `02-29` of a leap year, but a contract or organization might choose `03-01` in non-leap years. In that case, you must implement that policy explicitly.

## 6. Standalone Java 17+ example: adding and subtracting all units

Save the file `LocalDateMathDemo.java`:

~~~java
import java.time.LocalDate;

public class LocalDateMathDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2023, 1, 31);

        System.out.println("Original: " + start);
        System.out.println("+1 day:   " + start.plusDays(1));
        System.out.println("-2 days:  " + start.minusDays(2));
        System.out.println("+1 week:  " + start.plusWeeks(1));
        System.out.println("-2 weeks: " + start.minusWeeks(2));
        System.out.println("+1 month: " + start.plusMonths(1));
        System.out.println("-1 month: " + start.minusMonths(1));
        System.out.println("+1 year:  " + start.plusYears(1));
        System.out.println("-1 year:  " + start.minusYears(1));
        System.out.println("Still:    " + start);

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("Leap +1y: " + leapDay.plusYears(1));
        System.out.println("Leap +4y: " + leapDay.plusYears(4));
        System.out.println("March -1m: "
                + LocalDate.of(2024, 3, 31).minusMonths(1));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac LocalDateMathDemo.java
java LocalDateMathDemo
~~~

Deterministic stdout:

~~~text
Original: 2023-01-31
+1 day:   2023-02-01
-2 days:  2023-01-29
+1 week:  2023-02-07
-2 weeks: 2023-01-17
+1 month: 2023-02-28
-1 month: 2022-12-31
+1 year:  2024-01-31
-1 year:  2022-01-31
Still:    2023-01-31
Leap +1y: 2025-02-28
Leap +4y: 2028-02-29
March -1m: 2024-02-29
~~~

`start` remains `2023-01-31` because `LocalDate` is **immutable**. Calling `start.plusDays(1)` only creates a new result; it does not update the `start` variable. If you want to store the new date, you must assign it:

~~~java
LocalDate dueDate = LocalDate.of(2024, 5, 15);
dueDate = dueDate.plusWeeks(2); // dueDate = 2024-05-29
~~~

The two lines above are an **illustrative snippet** to place inside a method/class, not a standalone program. `LocalDate` is also thread-safe for sharing across threads because its object state cannot be modified.

## 7. Adding month by month can differ from adding multiple months at once

The end-of-month clamping rule leads to an important difference:

~~~text
2023-01-31
 + 1 month = 2023-02-28
 + 1 month = 2023-03-28

2023-01-31 + 2 months directly = 2023-03-31
~~~

Similarly, adding and then subtracting is not guaranteed to restore the original value:

~~~text
2023-01-31 + 1 month = 2023-02-28
2023-02-28 - 1 month = 2023-01-28
~~~

The order of two different operations can also change the result:

~~~text
2023-01-30 + 1 month + 2 days = 2023-03-02
2023-01-30 + 2 days + 1 month = 2023-03-01
~~~

Choosing the **anchor date** is especially important for recurring billing cycles. If each month you update `current = current.plusMonths(1)`, a starting anchor on the 31st can gradually "drift" to the 28th or 29th. If the contract requires "the 31st if available, otherwise the last day of the month", keep the original `anchor` and calculate period `n` with `anchor.plusMonths(n)`.

### Example: anchor and end-of-month

File `MonthPolicyDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.YearMonth;

public class MonthPolicyDemo {
    public static void main(String[] args) {
        LocalDate anchor = LocalDate.of(2023, 1, 31);

        LocalDate chained = anchor.plusMonths(1).plusMonths(1);
        LocalDate direct = anchor.plusMonths(2);
        LocalDate roundTrip = anchor.plusMonths(1).minusMonths(1);
        LocalDate monthEnd = YearMonth.from(anchor)
                .plusMonths(1)
                .atEndOfMonth();

        LocalDate orderA = LocalDate.of(2023, 1, 30)
                .plusMonths(1).plusDays(2);
        LocalDate orderB = LocalDate.of(2023, 1, 30)
                .plusDays(2).plusMonths(1);

        System.out.println("Chained: " + chained);
        System.out.println("Direct: " + direct);
        System.out.println("Round-trip: " + roundTrip);
        System.out.println("Next month end: " + monthEnd);
        System.out.println("Month then days: " + orderA);
        System.out.println("Days then month: " + orderB);
    }
}
~~~

Compile/run:

~~~bash
javac MonthPolicyDemo.java
java MonthPolicyDemo
~~~

Output:

~~~text
Chained: 2023-03-28
Direct: 2023-03-31
Round-trip: 2023-01-28
Next month end: 2023-02-28
Month then days: 2023-03-02
Days then month: 2023-03-01
~~~

**Rules for choosing the operation:**

- If you need to add one month from the **already-adjusted current date**, use `current.plusMonths(1)`.
- If you need "the `n`-th period from the **contract signing date**", use `anchor.plusMonths(n)` and keep the anchor unchanged.
- If you need the **last day of every month**, use `YearMonth.from(anchor).plusMonths(n).atEndOfMonth()`; for example, the next periods after January 2023 are `2023-02-28`, `2023-03-31`, `2023-04-30`.
- If a contract requires rolling day 31 over to the **1st of the next month**, or skipping non-existent dates, that is a custom policy and must be implemented explicitly. `plusMonths` does not know that rule.

## 8. Period, ChronoUnit, and measuring differences

Not every problem is "add an integer number of units".

`Period` represents a **calendar-based amount of time** consisting of years, months, and days. `Period.of(1, 2, 3)` has 1 year, 2 months, and 3 days; `Period.ofWeeks(2)` is stored as 14 days and prints as `P14D`. You can add a `Period` to a `LocalDate` via `date.plus(period)` or subtract it with `date.minus(period)`.

`ChronoUnit` provides generic units:

- `date.plus(3, ChronoUnit.MONTHS)` is equivalent to adding three months.
- `ChronoUnit.DAYS.between(a, b)` computes the signed number of calendar days between two dates; negative when `b` is before `a`.
- `ChronoUnit.WEEKS.between(a, b)` counts the number of complete weeks based on the day span.
- `ChronoUnit.MONTHS.between(a, b)` counts the number of **complete months**, which does not necessarily match the number of months `plusMonths` can reach due to the day-clamping rule.

File `CalendarDifferenceDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class CalendarDifferenceDemo {
    public static void main(String[] args) {
        LocalDate from = LocalDate.of(2024, 1, 31);
        LocalDate to = LocalDate.of(2024, 3, 1);
        Period calendarDifference = Period.between(from, to);

        System.out.println("Period: " + calendarDifference);
        System.out.println("Days: " + ChronoUnit.DAYS.between(from, to));
        System.out.println("After Period: " + from.plus(calendarDifference));
        System.out.println("Full months to Feb 29: "
                + ChronoUnit.MONTHS.between(
                        from, LocalDate.of(2024, 2, 29)));
        System.out.println("Two weeks: " + Period.ofWeeks(2));
        System.out.println("+3 months: "
                + from.plus(3, ChronoUnit.MONTHS));
    }
}
~~~

Compile/run:

~~~bash
javac CalendarDifferenceDemo.java
java CalendarDifferenceDemo
~~~

Stdout:

~~~text
Period: P1M1D
Days: 30
After Period: 2024-03-01
Full months to Feb 29: 0
Two weeks: P14D
+3 months: 2024-04-30
~~~

Why do these seemingly surprising results happen?

- `2024-01-31` to `2024-03-01` are **30 calendar days** apart; `Period.between` expresses this as **1 month and 1 day**.
- `ChronoUnit.MONTHS.between(2024-01-31, 2024-02-29)` returns **0 complete months** under the unit-counting rule, even though `2024-01-31.plusMonths(1)` is indeed `2024-02-29`. "Shifting forward by one calendar month" and "counting complete months between two dates" are two operations with different purposes.
- `Period.ofWeeks(2)` prints `P14D` because `Period` stores the number of days and does not maintain a separate weeks field.
- `plus(3, MONTHS)` from `2024-01-31` lands on `2024-04-30` because the target month has no 31st day.

When adding a `Period` that has years, months, and days, the operation applies the years and months components before the days. Do not convert `Period.of(0, 1, 3)` into "33 days" because month lengths vary. When calculating deadlines, clearly choose between `Period`/`ChronoUnit` and an absolute time span `Duration`.

## 9. Common business scenarios

### 9.1. Deadline after 14 calendar days

If the receipt date is `receivedDate`, the due date based on a 14-day span is:

~~~java
LocalDate deadline = receivedDate.plusDays(14);
~~~

This snippet is **not standalone** because `receivedDate` is supplied by the program. If the rule counts the receipt date as **day 1**, the 14th day may be `receivedDate.plusDays(13)`. Align on the exact terms and write boundary tests.

### 9.2. Monthly or annual billing

An original contract dated January 31 that specifies "the same day of the month if it exists, otherwise the end of the month" can be calculated as:

~~~java
LocalDate anchor = LocalDate.of(2023, 1, 31);
LocalDate first = anchor.plusMonths(1);  // 2023-02-28
LocalDate second = anchor.plusMonths(2); // 2023-03-31
~~~

This snippet is also an **illustrative snippet** that needs to be placed inside a method/class. If the contract term is "the last day of the month", prefer `YearMonth.atEndOfMonth()` to express the intent directly, even when the anchor is not a month-end date.

### 9.3. Adding business days

`plusDays(5)` is not five business days. For a schedule that only excludes Saturday and Sunday, you need to check `DayOfWeek`; for a real organizational calendar, you must also account for public holidays, observed/compensatory holidays, and regional calendars. Avoid hardcoding a two-day weekend if the system serves multiple countries.

### 9.4. Calculating dates in the user's time zone

`LocalDate.now()` uses the JVM's default time zone. If the user is in Tokyo while the server runs in UTC, the two sides can be on **two different calendar dates**.

~~~java
LocalDate todayInTokyo = LocalDate.now(
        java.time.ZoneId.of("Asia/Tokyo"));
~~~

This is an illustrative snippet and its result changes with real time, so it has no fixed stdout. In larger applications or unit tests, pass a `Clock` and call `LocalDate.now(clock)` to control the time source.

`LocalDate` only holds a calendar date; to convert the start of a day into an absolute point in time, you must provide a `ZoneId` (for example, `date.atStartOfDay(zone).toInstant()`) and accept the time zone rules in effect on that date.

## 10. Limits, error cases, and testing

`LocalDate` supports years from `-999999999` to `+999999999` in the proleptic ISO/Gregorian calendar system. Addition or subtraction outside the valid range can throw `DateTimeException`; some extremely large arithmetic operations can throw `ArithmeticException`. Validate your application's allowed date range and input unit counts.

Notes:

- `LocalDate.of(2023, 2, 29)` is invalid and throws `DateTimeException`.
- `LocalDate.of(2024, 4, 31)` is invalid and throws `DateTimeException`.
- `LocalDate.MAX.plusDays(1)` exceeds the supported range.
- `date.plus(1, ChronoUnit.HOURS)` does not apply to a date without a time component and throws `UnsupportedTemporalTypeException`.
- `date.withDayOfMonth(31)` does not clamp the day automatically like `plusMonths`.

Tests should cover both normal dates and boundary cases:

1. Feb 28 in a non-leap year plus one day → Mar 1; Feb 28 in a leap year → Feb 29.
2. Jan 31 plus one month in a non-leap year → Feb 28; in a leap year → Feb 29.
3. `2024-02-29` plus one year → `2025-02-28`; plus four years → `2028-02-29`.
4. Jan 31 plus two months directly differs from adding one month at a time.
5. Adding and then subtracting months does not necessarily restore the original date.
6. Counting days with `ChronoUnit.DAYS.between` has the right sign and matches inclusive/exclusive boundary rules.
7. Never lose the new `LocalDate` value by ignoring the return value.

## 11. Common mistakes

| Misconception or wrong approach | Consequence | Correct approach |
|---|---|---|
| "`plusDays` mutates the date object itself." | Original date is unchanged; result is discarded. | Capture the return value or reassign the variable. |
| "One month is 30 days." | Wrong at month-end and in leap years. | Use `plusMonths` for calendar months. |
| "One year is always 365 days." | Off by one when crossing a leap day. | Use `plusYears` and understand the Feb 29 rule. |
| "Adding months then subtracting months is always an inverse." | Jan 31 → Feb 28 → Jan 28. | Keep an anchor date for restoration or billing cycles. |
| "`plusMonths(1)` each cycle always keeps the 31st." | Recurring schedule drifts after February. | Compute period `n` from the anchor or `YearMonth`. |
| "`plusWeeks(1)` gives the start of next week." | Result keeps the same day of the week. | Use `DayOfWeek` and `TemporalAdjusters` for a target weekday. |
| "`plusDays(1)` means exactly 24 real hours." | Confuses calendar days with duration across DST. | Distinguish `LocalDate` from `Instant`/`Duration`. |
| "`ChronoUnit.MONTHS.between` is the exact inverse of `plusMonths`." | Unexpected results on month-end dates. | Pick the API that matches the calculation goal. |
| "Adding a year to Feb 29 always lands on Mar 1 in non-leap years." | Java defaults to Feb 28. | Encode a custom policy if the business requires Mar 1. |
| "Adding calendar days is the same as adding business days." | Deadlines are wrong when weekends/holidays intervene. | Combine with work calendars and holiday lists. |

## 12. Self-check questions

**1.** What does `LocalDate.of(2024, 1, 31).plusMonths(1)` return?

**Answer:** `2024-02-29` because 2024 is a leap year.

**2.** Is `LocalDate.of(2023, 1, 31).plusMonths(2)` equal to `plusMonths(1).plusMonths(1)`?

**Answer:** No. Adding directly gives `2023-03-31`, while chaining sequentially gives `2023-03-28`.

**3.** What does `LocalDate.of(2024, 2, 29).plusYears(1)` return?

**Answer:** `2025-02-28`; February 29 does not exist in 2025.

**4.** Why is "after 7 calendar days" not always "after exactly 168 hours" in local time?

**Answer:** `LocalDate` only identifies a calendar date; some regions change offsets (DST), so two instants at the same local time seven calendar days apart can have an elapsed duration other than 168 hours.

**5.** What should you choose to compute the last day of the next month?

**Answer:** `YearMonth.from(date).plusMonths(1).atEndOfMonth()` when the policy is truly "the last day of each month".

**6.** What string does `Period.ofWeeks(2)` print as?

**Answer:** `P14D` because `Period` stores 14 days in its days field and does not store a separate weeks field.

## Key takeaways

**Days/weeks** move by calendar day count; **months/years** move by calendar structure and **clamp to the last valid day of the month** when the original day does not exist in the target month/year. `LocalDate` is immutable and holds no time or time zone. When building recurring schedules, choose your anchor, month-end policy, and leap-year policy explicitly. Use `Period`, `ChronoUnit`, or `YearMonth` when they match your business intent, and never equate calendar days with absolute elapsed durations.
