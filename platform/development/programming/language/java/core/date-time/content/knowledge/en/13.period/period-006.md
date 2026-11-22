# Adding and Subtracting Period and Order of Application to Dates in Java

## 1. Period describes calendar changes, not a fixed number of days

`java.time.Period` represents a period of time in terms of **calendar years, months, and days**. It is suitable for requirements such as "add one month to the billing date", "add two years", "go back three days", or "calculate the calendar distance between two dates".

Unlike `Duration`, which typically expresses duration in seconds and nanoseconds, `Period` does not convert everything into a fixed number of seconds or days. A month can have 28, 29, 30, or 31 days; a year can have 365 or 366 days. Therefore, adding one month to the 31st may cause the resulting date to be adjusted to the end of the month.

Important example:

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);

System.out.println(start.plusMonths(1));
System.out.println(start.plus(Period.ofMonths(1)));
System.out.println(start.plus(Period.ofMonths(2)));
System.out.println(start.plusMonths(1).plusMonths(1));
~~~

Stdout:

~~~text
2023-02-28
2023-02-28
2023-03-31
2023-03-28
~~~

The first two ways are equivalent in this example: adding **one calendar month** from 2023-01-31 means 2023-02-31 does not exist, so the result is adjusted to the last day of February, i.e., 2023-02-28. However, "adding two months at once" and "adding one month twice" can differ, because the first addition changes the date used for the subsequent calculation.

This is the core theme: `Period` is a tuple of year/month/day components; it **does not store a sequence of date operations that were performed**. When a specific order is needed, look at which date each call is being applied to.

## 2. Creating and reading Period

Common factory methods:

~~~java
Period days = Period.ofDays(10);
Period months = Period.ofMonths(2);
Period years = Period.ofYears(1);
Period mixed = Period.of(1, 2, 3);
Period parsed = Period.parse("P1Y2M3D");
~~~

`Period.of(years, months, days)` data consists of three integer fields:

| Creation | Calendar value | `toString()` |
|---|---|---|
| `Period.ofDays(10)` | 10 days | `P10D` |
| `Period.ofMonths(2)` | 2 months | `P2M` |
| `Period.ofYears(1)` | 1 year | `P1Y` |
| `Period.of(1, 2, 3)` | 1 year, 2 months, 3 days | `P1Y2M3D` |
| `Period.ZERO` | No change to years/months/days | `P0D` |

ISO-8601 strings start with `P` for period; `Y` is years, `M` in the year-month part is months, and `D` is days. For example, `Period.parse("P1Y2M3D")` creates a Period consisting of 1 year, 2 months, and 3 days.

Reader methods include:

- `getYears()`: number of years.
- `getMonths()`: number of months in the **month component**, not the total months combined with years.
- `getDays()`: number of days in the **day component**.
- `isZero()`: whether the period is zero.
- `isNegative()`: whether at least one component is negative.
- `toTotalMonths()`: converts years and months into total months; does **not** include days because a day has no fixed conversion to months.

Note that `Period.of(1, 14, 3)` can still keep the months field as 14. `Period` does not automatically normalize all values into "0–11 months" upon creation; call `normalized()` if you want to roll every 12 months into one year.

## 3. How Period is applied to LocalDate

`LocalDate.plus(Period)` applies the **years and months** components first, and then applies **days**. Adding a period can be understood as the following calendar procedure:

1. Add the years and months to the initial date as a total number of months.
2. If the original day-of-month does not exist in the resulting month, adjust to the last valid day of that month.
3. Add the number of days in the period to the resulting date.

Example:

~~~java
LocalDate jan31 = LocalDate.of(2023, 1, 31);
Period oneMonthMinusOneDay = Period.ofMonths(1).minusDays(1);

System.out.println(jan31.plus(oneMonthMinusOneDay));
System.out.println(jan31.plusMonths(1).minusDays(1));
~~~

Stdout:

~~~text
2023-02-27
2023-02-27
~~~

Reason: the month-addition step brings 2023-01-31 to 2023-02-28, because February 2023 only has 28 days. Then subtracting one day gives 2023-02-27.

### 3.1. Adding a Period applies components, not repeated operations

Do not read `Period.ofMonths(2)` as "call plusMonths(1) twice". It means **adding two months in a single calendar calculation**:

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);

LocalDate twoMonthsAtOnce = start.plus(Period.ofMonths(2));
LocalDate oneMonthTwice =
        start.plusMonths(1).plusMonths(1);

System.out.println(twoMonthsAtOnce);
System.out.println(oneMonthTwice);
~~~

Stdout:

~~~text
2023-03-31
2023-03-28
~~~

Explanation:

- Adding two months directly: 31/01 + 2 months = 31/03; the 31st exists in March.
- Adding one month the first time: 31/01 → 28/02 (the 31st does not exist).
- Adding another month from the 28/02 result: 28/02 → 28/03.

**The date after the first addition becomes the input for the second addition.** The information that the original day was 31 is no longer present in the value 28/02, so the second step cannot "restore" the 31st.

This difference affects monthly billing schedules, due dates, recurring day-of-month schedules, and year-end calculations. If you want "the last day of each month", do not repeatedly add months from an already-adjusted date and assume you will always get the end of the month; use an explicit end-of-month policy, such as `YearMonth.atEndOfMonth()`.

## 4. Order of addition and subtraction matters

Date calculations are generally **not commutative**. That means swapping the order of two operations can produce different results:

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);

LocalDate a = start.plusMonths(1).minusDays(1);
LocalDate b = start.minusDays(1).plusMonths(1);

System.out.println(a);
System.out.println(b);
~~~

Stdout:

~~~text
2023-02-27
2023-02-28
~~~

Details:

- `a`: 31/01 + 1 month → 28/02; minus 1 day → 27/02.
- `b`: 31/01 − 1 day → 30/01; plus 1 month → 28/02.

Both expressions use the same month and day units, yet produce different results because the date is adjusted at different points.

### 4.1. A combined Period does not record operation order

Consider:

~~~java
Period p = Period.ofMonths(1).minusDays(1);
LocalDate combined = LocalDate.of(2023, 1, 31).plus(p);
~~~

`combined` is `2023-02-27` because the period contains the fields `months = 1` and `days = -1`; when applied, Java adds months first and then adds days.

No history is stored to indicate that the creator of the period called "subtract day first, add month later". Both of the following:

~~~java
Period p1 = Period.ofMonths(1).minusDays(1);
Period p2 = Period.ofDays(-1).plusMonths(1);

System.out.println(p1);
System.out.println(p2);
~~~

Both represent `P1M-1D`. Adding either object to a `LocalDate` follows the same component-application rule of `Period`. If the business logic requires the order "subtract one day first, then add one month", keep the two separate calls on `LocalDate`:

~~~java
LocalDate ordered = start.minusDays(1).plusMonths(1);
~~~

Do not combine them into a single `Period` expecting it to preserve the order.

## 5. Order inside a Period with years, months, and days

For `Period.of(1, 2, 3)`, Java applies years/months as total months and then adds days. Example:

~~~java
LocalDate start = LocalDate.of(2020, 2, 29);
Period p = Period.of(1, 1, 1);

System.out.println(start.plus(p));
~~~

Stdout:

~~~text
2021-03-30
~~~

Walkthrough:

1. Add one year and one month: 29/02/2020 + 13 months → 29/03/2021. The 29th exists in March.
2. Add one day → 30/03/2021.

For dates that do not exist in the target month, the year/month part also adjusts the day to the end of the month before adding the day part. Example:

~~~java
LocalDate start = LocalDate.of(2020, 2, 29);
System.out.println(start.plus(Period.ofYears(1)));
System.out.println(start.plus(Period.ofYears(1).plusDays(1)));
~~~

Stdout:

~~~text
2021-02-28
2021-03-01
~~~

Adding one year from 29/02/2020 → 28/02/2021, then adding one day → 01/03/2021. This **differs** from assuming "one year is always 365 days"; `Period` operates according to calendar rules.

## 6. Subtracting Period: negative signs and two equivalent ways to write it

You can subtract a period using `minus(Period)`:

~~~java
LocalDate date = LocalDate.of(2024, 3, 31);

System.out.println(date.minus(Period.ofMonths(1)));
System.out.println(date.plus(Period.ofMonths(-1)));
System.out.println(date.minusMonths(1));
~~~

All three results are `2024-02-29`. Because February in the leap year 2024 has 29 days, 31/03 minus one month is adjusted to the last day of February.

`Period.negated()` flips the sign of each component; `Period.multipliedBy(-1)` also creates a negated period. Example:

~~~java
Period p = Period.of(1, 2, 3);
System.out.println(p.negated());
System.out.println(p.multipliedBy(-1));
~~~

Both print `P-1Y-2M-3D`.

Note: a `Period` can have fields with **opposite signs**, such as `P1M-1D`. `isNegative()` returns `true` if **any component is negative**, even when other positive components make the period feel "overall" positive. For a mixed period, there is no fixed total number of days to judge its length; you must apply it to a specific date to know the result.

## 7. Period.between(): calendar distance depends on two dates

`Period.between(start, end)` returns the period from the start date to the end date; the sign depends on the order of the two dates. Example:

~~~java
LocalDate start = LocalDate.of(2023, 1, 15);
LocalDate end = LocalDate.of(2023, 6, 1);

System.out.println(Period.between(start, end));
System.out.println(Period.between(end, start));
~~~

Stdout:

~~~text
P4M17D
P-4M-17D
~~~

From 2023-01-31 to 2023-02-28:

~~~java
System.out.println(Period.between(
        LocalDate.of(2023, 1, 31),
        LocalDate.of(2023, 2, 28)));
~~~

Result:

~~~text
P28D
~~~

`Period.between` does not divide the total number of days into "exact 30-day months". The result depends on the start/end dates and calendar rules. If you only need the absolute number of days between two ISO dates, use:

~~~java
long days = ChronoUnit.DAYS.between(start, end);
~~~

For two `LocalDate` values, `ChronoUnit.DAYS.between` gives the total number of days between them. `Period` is appropriate when you need to represent a year/month/day calendar offset for display and reapplication.

A business note: `Period.between(a, b)` does not guarantee `a.plus(Period.between(a, b)).equals(b)` for every possible combination? For `LocalDate`, `Period` is produced to represent the calendar distance using the `until` algorithm and adding it back generally restores the target date; however, you should not use a rounded `Period` or manually edit its components as if it were a fixed duration. Test round-trips on real data ranges if month-end dates, leap years, or negative periods are significant to the business logic.

## 8. normalized(): normalizing months into years

`Period.normalized()` converts the month part into years and remaining months, so that months lie in the range -11 to 11 with the sign consistent with the year/month normalization:

~~~java
Period original = Period.of(1, 14, 3);
System.out.println(original);
System.out.println(original.normalized());
~~~

Stdout:

~~~text
P1Y14M3D
P2Y2M3D
~~~

`normalized()` does **not** convert days into months or years; it only normalizes the 12 months = 1 year relationship. Because months have varying numbers of days, `P1M30D` cannot be normalized into a single calendar-equivalent form based on day count.

~~~java
System.out.println(Period.ofMonths(1).plusDays(30));
~~~

Stdout:

~~~text
P1M30D
~~~

`P1M30D` does not always mean two months. Starting from 01/01 it can yield 02/03 or 03/02 depending on the year/month, whereas adding two months directly to a specific date follows different rules. Do not use `toTotalMonths()` to convert an entire period containing days into a number of months; that method only computes `years * 12 + months` and ignores the days part.

### 8.1. Not every mixed-sign Period "normalizes to uniform positive/negative"

A `Period` is allowed to have year/month/day components with different signs. For example, `P1M-40D`. `normalized()` does not resolve actual month lengths to make all fields share the same sign, because the start date must be known to determine month length.

Do not write logic like:

~~~java
if (period.toTotalMonths() > 0) {
    // Assuming the entire period is positive
}
~~~

if the period has a negative days component. `toTotalMonths()` can be positive while `getDays()` is negative. Inspect each component individually, or apply it to a specific date and compare the resulting date if that is what the business logic needs to know.

## 9. Distinguishing Period and Duration

| Characteristic | `Period` | `Duration` |
|---|---|---|
| Primary units | Calendar years, months, days | Seconds and nanoseconds |
| Used with | `LocalDate`, calendar dates | `Instant`, `Duration.between`; compatible time types |
| Months | A calendar component, not a fixed number of days | No month unit |
| Days | One calendar day | 24 hours of duration when expressed as `Duration.ofDays(1)` |
| Adding to ZonedDateTime | Adds calendar days per date/zone rules | Adds elapsed duration |
| Can adding repeatedly differ from adding once? | Yes, due to month-end adjustment | Typically adds total seconds/nanos, though local view can shift across DST |

Important example for zoned calendar dates:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, zone);

System.out.println(start.plus(Period.ofDays(1)));
System.out.println(start.plus(Duration.ofDays(1)));
~~~

When New York begins DST, the next calendar day can be only 23 hours after the initial instant. Adding `Period.ofDays(1)` preserves the meaning of **the same local time on the next day**, whereas `Duration.ofDays(1)` adds exactly 24 elapsed hours and may result in a local time one hour later.

Use `Period` when the requirement is **calendar dates** ("tomorrow", "add one month", "payment due date"), and `Duration` when the requirement is **elapsed time** ("after exactly 24 hours", "30-second timeout"). Do not implicitly mix the two meanings.

## 10. Standalone Java program: order of application

Save in file **`PeriodOrderDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class PeriodOrderDemo {
    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2023, 1, 31);

        LocalDate oneMonthTwice =
                jan31.plusMonths(1).plusMonths(1);
        LocalDate twoMonthsOnce =
                jan31.plus(Period.ofMonths(2));

        LocalDate monthThenMinusDay =
                jan31.plusMonths(1).minusDays(1);
        LocalDate dayThenMonth =
                jan31.minusDays(1).plusMonths(1);

        System.out.println("One month twice: " + oneMonthTwice);
        System.out.println("Two months at once: " + twoMonthsOnce);
        System.out.println("Month then minus day: " + monthThenMinusDay);
        System.out.println("Minus day then month: " + dayThenMonth);
        System.out.println("Period between: " + Period.between(
                jan31, LocalDate.of(2023, 2, 28)));
        System.out.println("Days between: " + ChronoUnit.DAYS.between(
                jan31, LocalDate.of(2023, 2, 28)));
    }
}
~~~

Compile and run:

~~~bash
javac PeriodOrderDemo.java
java PeriodOrderDemo
~~~

Stdout:

~~~text
One month twice: 2023-03-28
Two months at once: 2023-03-31
Month then minus day: 2023-02-27
Minus day then month: 2023-02-28
Period between: P28D
Days between: 28
~~~

The output shows that **order and starting point** determine month-end adjustment behavior. When reading code with chained method calls, trace it from left to right using concrete intermediate dates; do not replace a chain of operations with a combined `Period` unless you have verified that the two approaches are equivalent.

## 11. Common pitfalls and how to avoid them

1. **Treating a month as 30 days:** incorrect. Months can have 28–31 days; years can also be leap years.
2. **Treating `Period.ofMonths(2)` as two calls to `plusMonths(1)`:** the month-end day may be adjusted on the first call and change the result of the next call.
3. **Combining additions/subtractions and assuming order is preserved:** `Period` stores components, not call history. Keep separate calls if business order matters.
4. **Assuming every resulting date keeps the original day of month:** 31/01 + 1 month is 28/02 or 29/02 depending on the year.
5. **Using Period as a duration for timeouts:** `Period` carries calendar components; use `Duration` or `Instant` for absolute amounts of time.
6. **Using `toTotalMonths()` on a period that has a days component:** it ignores days, so it is not the actual total months.
7. **Thinking `normalized()` normalizes all components:** it only rolls months into years; it does not convert days into months.
8. **Ignoring mixed-sign Periods:** `P1M-40D` has a positive month field and a negative day field; you cannot determine the "overall" sign from total months alone.
9. **Misunderstanding `Period.between` as a fixed number of days divided into months:** the result follows calendar rules; use `ChronoUnit.DAYS.between` if you need total days.
10. **Using `P1M-1D` to represent the sequence "subtract day then add month":** it does not store order. Write the date operations sequentially.
11. **Adding one day to a ZonedDateTime and assuming exactly 24 hours have elapsed:** DST can make a calendar day 23 or 25 hours long.
12. **Overlooking leap years:** 29/02 + 1 year can become 28/02 the next year; subsequent day additions continue from that adjusted date.
13. **Not testing negative data ranges:** subtracting and negative `Period` values can produce different results from reversing a positive addition due to month-end adjustment.
14. **Using Period as a recurring end-of-month policy:** recurring end-of-month schedules should be recomputed from `YearMonth` or an "end of month" rule rather than relying solely on the date from the previous addition.

## 12. Self-check questions

**Question 1.** What is the result of `LocalDate.of(2023,1,31).plus(Period.ofMonths(2))`? Why does it differ from adding one month twice?

**Answer:** `2023-03-31`. Two months are added in a single calculation. Adding one month twice goes 31/01 → 28/02 → 28/03 because the first step already adjusted the date to the end of the month.

**Question 2.** Compare `start.plusMonths(1).minusDays(1)` with `start.minusDays(1).plusMonths(1)` for `start = 2023-01-31`.

**Answer:** The results are `2023-02-27` and `2023-02-28`, respectively; the order of operations is not commutative.

**Question 3.** What does `Period.of(1,14,3).normalized()` return?

**Answer:** `P2Y2M3D`, because 14 months is converted to 1 year and 2 months; the days component remains unchanged.

**Question 4.** Can `Period.ofMonths(1).plusDays(30).normalized()` be converted into two months?

**Answer:** There is no such general calendar conversion. `normalized()` only normalizes months/years; a month does not have a fixed number of days.

**Question 5.** Why is `Period.between(2023-01-31, 2023-02-28)` equal to `P28D`?

**Answer:** According to `LocalDate`'s calendar-distance algorithm, the distance from January 31 to February 28 of that year is represented as 28 days. `Period` does not force every month to have a fixed length.

**Question 6.** When should you use Period, and when should you use Duration?

**Answer:** `Period` for calendar date changes in years/months/days; `Duration` for durations in seconds/nanoseconds. A 24-hour timeout uses `Duration`; a due date in the following month uses `Period` or the corresponding calendar operation.

**Question 7.** Does `P1M-1D` store the information that the day must be subtracted before adding the month?

**Answer:** No. It stores fields of 1 month and -1 day. When applied to a `LocalDate`, the month part is applied before the day part.

**Question 8.** Why must you be careful when adding a Period multiple times?

**Answer:** Because the intermediate date after each addition may have been adjusted to the end of the month. The next addition uses that intermediate date as its input, which can produce a different result from adding the total number of months all at once.

## 13. Practical rules

- Read `Period` as **three calendar components**, not as a fixed number of days.
- When applying it to `LocalDate`, remember that years/months are processed before days; a day that does not exist in the target month is adjusted to the end of that month.
- If business logic specifies multiple ordered steps, keep those steps directly on the date; do not merge them into a single `Period` expecting it to preserve the order.
- When you want to add two months from the original date, use a single two-month addition. When you want a recurring monthly rule, explicitly define the anchor date / end-of-month adjustment so each period's result stays consistent.
- Choose `Period` for calendar changes and `Duration` for elapsed time. With `ZonedDateTime`, a calendar day and 24 elapsed hours can produce different results around DST.
- Test at least the 29th/30th/31st, February, leap years, negative/mixed-sign `Period`s, and multi-step addition/subtraction chains.

When performing date calculations in Java, **the order of application is part of the business meaning**. Understanding how `Period` stores components and how `LocalDate` adjusts month-end dates helps prevent incorrect payment due dates, recurring schedules, and inter-period date calculations.