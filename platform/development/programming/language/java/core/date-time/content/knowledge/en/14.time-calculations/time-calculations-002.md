# plusMonths() at End of Month and the Non-Reversibility of Time Calculations

In the Java Date-Time API (`java.time`), `plusMonths(...)` and `minusMonths(...)` perform **calendar-based** calculations rather than adding or subtracting a fixed number of seconds. When the original day does not exist in the target month, Java adjusts it to the last valid day of that month. Therefore, **adding one month and then subtracting one month does not always restore the original date**.

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);
LocalDate next = start.plusMonths(1); // 2023-02-28
LocalDate back = next.minusMonths(1); // 2023-01-28
~~~

The result is `2023-01-28`, not `2023-01-31`. Day 31 was adjusted when moving to February 2023; the intermediate value no longer retains the intent that “the desired day is 31”.

## 1. End-of-Month Adjustment Rules

For `LocalDate.plusMonths(n)`, Java computes the target month, keeps the current day of the month if it exists in the target month, and otherwise selects the last day of the target month.

| Original Date | Operation | Result | Explanation |
|---|---|---|---|
| `2023-01-15` | `plusMonths(1)` | `2023-02-15` | Day 15 exists |
| `2023-01-31` | `plusMonths(1)` | `2023-02-28` | February 2023 has 28 days |
| `2024-01-31` | `plusMonths(1)` | `2024-02-29` | 2024 is a leap year |
| `2024-03-31` | `minusMonths(1)` | `2024-02-29` | February 2024 has 29 days |
| `2024-05-31` | `plusMonths(1)` | `2024-06-30` | June has 30 days |

This is valid behavior according to the ISO calendar, not a bug or exception. The calculations keep the date valid within the calendar; they do not retain information about the desired day prior to adjustment.

Leap years also matter:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);
System.out.println(leapDay.plusYears(1)); // 2025-02-28
~~~

The year 2025 does not have February 29, so the result is adjusted to 2025-02-28.

## 2. Why Addition and Subtraction Are Not Reversible

A transformation cannot be undone if the intermediate value has lost information. From `2023-02-28`, Java cannot tell whether the user originally wanted the 28th or started from the 31st and was adjusted.

~~~text
2023-01-31
    | plusMonths(1)
    v
2023-02-28  (day 31 does not exist)
    | minusMonths(1)
    v
2023-01-28  (does not return to day 31)
~~~

~~~java
LocalDate jan31 = LocalDate.of(2023, 1, 31);
LocalDate feb28 = jan31.plusMonths(1);
LocalDate returned = feb28.minusMonths(1);

System.out.println("start = " + jan31);
System.out.println("after plus = " + feb28);
System.out.println("after minus = " + returned);
System.out.println("restored = " + returned.equals(jan31));
~~~

~~~text
start = 2023-01-31
after plus = 2023-02-28
after minus = 2023-01-28
restored = false
~~~

Therefore, `minusMonths(1)` is not a general “undo” operation for `plusMonths(1)`. This rule also affects `plusYears(1)` on leap days.

## 3. Adding One Month at a Time vs. Adding Multiple Months at Once

How you split the calculation steps can also change the result:

~~~java
LocalDate jan31 = LocalDate.of(2023, 1, 31);
LocalDate oneMonthTwice = jan31.plusMonths(1).plusMonths(1);
LocalDate twoMonthsOnce = jan31.plusMonths(2);
System.out.println("one month twice = " + oneMonthTwice);
System.out.println("two months once = " + twoMonthsOnce);
~~~

~~~text
one month twice = 2023-03-28
two months once = 2023-03-31
~~~

The first addition turns January 31 into February 28. The second addition starts from day 28 and thus lands on March 28. However, adding two months directly starts from January 31 and lands in March, where day 31 exists.

Thus, `date.plusMonths(1).plusMonths(1)` is not necessarily equal to `date.plusMonths(2)`. For billing schedules, reminders, or contract renewals, you must define the rule clearly: whether each period is calculated from the adjusted date, from the original preferred day, or as the last day of the month.

## 4. Building Recurring Schedules by Intent

### Cumulative from the Previous Period

If each subsequent period is calculated from the actual date of the previous period, use `current.plusMonths(1)`. For example, Jan 31 → Feb 28 → Mar 28. This is a cumulative schedule, and shifting to day 28 after a short month is part of the rule.

### Preserving a Preferred Day Across Months

If the intent is “day 31 when the month has it; otherwise the last day of the month; and return to day 31 in later months when possible,” store the preferred day separately rather than accumulating on the adjusted value.

~~~java
import java.time.LocalDate;
import java.time.YearMonth;

static LocalDate dateInTargetMonth(YearMonth targetMonth, int preferredDay) {
    int day = Math.min(preferredDay, targetMonth.lengthOfMonth());
    return targetMonth.atDay(day);
}
~~~

This is an illustrative helper method to be placed inside a Java class, not a standalone program. Example using the preferred day from the original date:

~~~java
LocalDate original = LocalDate.of(2023, 1, 31);
YearMonth march = YearMonth.from(original).plusMonths(2);
LocalDate target = dateInTargetMonth(march, original.getDayOfMonth());
// 2023-03-31
~~~

Real applications should store the original intent (the preferred day or end-of-month rule) alongside the actual date of each period.

### Always Choosing the End of the Month

When the business requirement specifies “the last day of every month,” use `YearMonth.atEndOfMonth()`:

~~~java
YearMonth february = YearMonth.of(2023, 2);
LocalDate last = february.atEndOfMonth(); // 2023-02-28
~~~

For February in a leap year, the API returns day 29. Adding months on `YearMonth` and calling `atEndOfMonth()` expresses the goal more accurately than hardcoding day 28, 30, or 31.

## 5. LocalDateTime and ZonedDateTime

`LocalDateTime.plusMonths(...)` uses the same calendar date adjustment rules, while the time portion is generally preserved:

~~~java
LocalDateTime dt = LocalDateTime.of(2023, 1, 31, 10, 15);
System.out.println(dt.plusMonths(1)); // 2023-02-28T10:15
System.out.println(dt.plusMonths(1).minusMonths(1));
// 2023-01-28T10:15
~~~

With `ZonedDateTime`, Java also applies time zone rules at the target date and time. The local time may fall into a DST gap (non-existent time) or overlap (ambiguous time), causing the hour or offset to be adjusted.

~~~java
ZonedDateTime zoned = ZonedDateTime.of(
        2024, 3, 31, 2, 30, 0, 0, ZoneId.of("Europe/Paris"));
System.out.println("zoned source = " + zoned);
System.out.println("zoned + month = " + zoned.plusMonths(1));
System.out.println("zoned round trip = " +
        zoned.plusMonths(1).minusMonths(1));
~~~

~~~text
zoned source = 2024-03-31T03:30+02:00[Europe/Paris]
zoned + month = 2024-04-30T03:30+02:00[Europe/Paris]
zoned round trip = 2024-03-30T03:30+01:00[Europe/Paris]
~~~

March 31, 2024 at 02:30 does not exist in Paris under the test environment's DST rules, so Java adjusts it forward to 03:30 as soon as the value is created. Adding a month adjusts day 31 to day 30 of April; subtracting a month does not restore the original value. When debugging, distinguish end-of-month date adjustment from time zone gap/overlap resolution.

## 6. Other Transformations That Can Be Non-Reversible

| Transformation | Reason | Example |
|---|---|---|
| `plusMonths(1)` at end of month | Day missing in target month is adjusted | Jan 31 → Feb 28 |
| `plusYears(1)` from a leap day | Feb 29 does not exist in a common year | 2024-02-29 → 2025-02-28 |
| `truncatedTo(ChronoUnit.MINUTES)` | Seconds and nanoseconds are discarded | 10:15:42.5 → 10:15 |
| `Instant.toEpochMilli()` | Sub-millisecond precision is lost | Nanoseconds are dropped |
| Resolving DST gap/overlap times | Zone rules may select or adjust the time | Local time may shift |

Distinguish **calendar-based** adjustment from **precision loss**. Both can leave the result without enough information to recover the original input.

## 7. Standalone Java 17 Program

Save as **`MonthArithmeticDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZonedDateTime;
import java.time.ZoneId;

public class MonthArithmeticDemo {
    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2023, 1, 31);
        LocalDate feb28 = jan31.plusMonths(1);
        LocalDate back = feb28.minusMonths(1);
        System.out.println("Jan 31 + 1 month = " + feb28);
        System.out.println("then - 1 month = " + back);
        System.out.println("round trip restored = " + back.equals(jan31));

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("leap day + 1 year = " + leapDay.plusYears(1));
        System.out.println("Jan 31 + 2 months = " + jan31.plusMonths(2));
        System.out.println("Jan 31 + Period 2 months = " +
                jan31.plus(Period.ofMonths(2)));

        LocalDateTime dt = LocalDateTime.of(2023, 1, 31, 10, 15);
        System.out.println("datetime + month = " + dt.plusMonths(1));
        System.out.println("datetime then back = " +
                dt.plusMonths(1).minusMonths(1));

        ZonedDateTime zoned = ZonedDateTime.of(
                2024, 3, 31, 2, 30, 0, 0, ZoneId.of("Europe/Paris"));
        System.out.println("zoned source = " + zoned);
        System.out.println("zoned + month = " + zoned.plusMonths(1));
        System.out.println("zoned round trip = " +
                zoned.plusMonths(1).minusMonths(1));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac MonthArithmeticDemo.java
java MonthArithmeticDemo
~~~

Verified output with `javac --release 17`:

~~~text
Jan 31 + 1 month = 2023-02-28
then - 1 month = 2023-01-28
round trip restored = false
leap day + 1 year = 2025-02-28
Jan 31 + 2 months = 2023-03-31
Jan 31 + Period 2 months = 2023-03-31
datetime + month = 2023-02-28T10:15
datetime then back = 2023-01-28T10:15
zoned source = 2024-03-31T03:30+02:00[Europe/Paris]
zoned + month = 2024-04-30T03:30+02:00[Europe/Paris]
zoned round trip = 2024-03-30T03:30+01:00[Europe/Paris]
~~~

## 8. Common Mistakes

| Misconception | Why It Is Wrong | Correct Approach |
|---|---|---|
| Assuming adding one month and subtracting it restores the value | The original day may have been adjusted | Test with days 28–31 and leap years |
| Adding months sequentially while expecting day 31 every time | Later steps receive the adjusted intermediate date | Store the preferred day and compute per target period |
| Hardcoding day 30 for “end of month” | Months have different lengths | Use `YearMonth.atEndOfMonth()` |
| Treating `Period.ofMonths(1)` as a fixed 30 days | `Period` is a calendar-based amount | Use `Duration` for fixed second/hour durations |
| Ignoring DST on `ZonedDateTime` | Local time/offset may be adjusted | Check `ZoneId` and DST rules |
| Using a timestamp to store “end of month” intent | `Instant` is just a point in time and holds no recurrence rule | Store the appropriate calendar rule and zone |
| Relying on inverse arithmetic to recover data | Lost information cannot be reliably inferred | Store the original value or business metadata |

## 9. Self-Check

1. What date does `LocalDate.of(2023, 1, 31).plusMonths(1)` return? **2023-02-28**.
2. What do you get by subtracting one month from that result? **2023-01-28**, not day 31.
3. Why is it non-reversible? **Day 31 was adjusted to the last day of February; the intermediate value no longer retains the original desired day**.
4. Are adding one month twice and adding two months directly always the same? **No**: March 28 vs. March 31 in the example.
5. What does 2024-02-29 plus one year become? **2025-02-28**.
6. Which API directly expresses the “end of month” rule? **`YearMonth.atEndOfMonth()`**.
7. Does `LocalDateTime.plusMonths` preserve the time of day? **Yes**, while adjusting the date according to the calendar.
8. Why is `ZonedDateTime` more complex? **It must also resolve offsets and the zone's DST rules**.
9. If you need to preserve day 31 as the target for future periods, what should you do? **Store the preferred day or end-of-month policy instead of accumulating from the adjusted date**.

**Takeaway:** `plusMonths()` follows the calendar and clamps non-existent days to the end of the month. Because of this, month addition and subtraction are not always reversible, and multi-step additions can differ from a single addition. For recurring schedules, explicitly define whether the intent is “cumulative”, “preserve preferred day”, or “end of month”; with `ZonedDateTime`, also account for time zones and DST.

### References

- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html)
- [Java SE 17 — Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html)
