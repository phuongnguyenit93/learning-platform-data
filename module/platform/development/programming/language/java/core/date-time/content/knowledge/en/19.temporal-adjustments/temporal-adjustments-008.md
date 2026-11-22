# Testing Adjustment Rules at Month-End and Leap Years

## 1. Why Do Month-End Dates Need Separate Testing?

In date adjustment operations, tricky cases arise when the original day does not exist in the target month or year: moving day 31 into February, moving February 29 into a common year, or moving the last day of February into March. To test properly, separate three questions:

1. What is the target month or year?
2. How does the Java method handle an invalid day?
3. Does that result match the intended business rule?

A calendar-valid date is not necessarily the right due date. For example, `2024-02-29.plusMonths(1)` produces March 29, which is valid, yet it does not satisfy the requirement "always settle on the last day of the month."

This lesson uses `LocalDate`, which represents an ISO calendar date without a time of day or time zone. The goal is to predict, verify, and choose date adjustment rules; it does not yet convert dates into instants for task scheduling.

## 2. Not Every Operation Adjusts Dates the Same Way

With `plusMonths` and `plusYears`, picture two steps: compute the target month/year, then keep the day-of-month if it is still valid; otherwise, use the last valid day of the target month. `withMonth` and `withYear` also clamp the day down when needed.

Conversely, creating a non-existent date directly or setting an invalid day-of-month throws an exception. You cannot assume "Java always clamps dates automatically" just because `plusMonths` does. See the official [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html) contract.

| Requirement | Operation | Result |
| --- | --- | --- |
| Move to February of a common year | `LocalDate.of(2023, 1, 31).plusMonths(1)` | `2023-02-28` |
| Move to February of a leap year | `LocalDate.of(2024, 1, 31).plusMonths(1)` | `2024-02-29` |
| Step back from March to February | `LocalDate.of(2024, 3, 31).minusMonths(1)` | `2024-02-29` |
| Change month, keep year | `LocalDate.of(2024, 1, 31).withMonth(2)` | `2024-02-29` |
| Change year of a leap day | `LocalDate.of(2024, 2, 29).withYear(2023)` | `2023-02-28` |
| Add one year from a leap day | `LocalDate.of(2024, 2, 29).plusYears(1)` | `2025-02-28` |
| Create a non-existent date | `LocalDate.of(2023, 2, 29)` | `DateTimeException` |
| Set day 30 in February | `LocalDate.of(2024, 2, 15).withDayOfMonth(30)` | `DateTimeException` |
| Set an out-of-range month | `LocalDate.of(2024, 1, 31).withMonth(13)` | `DateTimeException` |

You must distinguish "day 31 does not exist in the target month" from "month 13." Clamping to the last day of the month does not turn every invalid input into a valid one.

Nor should you substitute 30 days for one month: from 2024-01-31, adding one month yields 2024-02-29, whereas adding 30 days yields 2024-03-01. `plusDays` advances along the calendar by a number of days and does not apply the rule of preserving the day-of-month.

## 3. Leap Years: Also Check Century-Year Exceptions

Under the ISO calendar used by these types, a year divisible by 4 is usually a leap year; a year divisible by 100 is not a leap year unless it is also divisible by 400. Therefore:

| Year | Leap Year? | Last Day of February |
| --- | --- | --- |
| 1900 | No | `1900-02-28` |
| 2000 | Yes | `2000-02-29` |
| 2023 | No | `2023-02-28` |
| 2024 | Yes | `2024-02-29` |
| 2100 | No | `2100-02-28` |

In application code, use `Year.isLeap(year)` or `YearMonth.of(year, month).lengthOfMonth()` instead of duplicating the formula in multiple places. The length of February must be tied to a specific year, so storing only "February" is not enough to determine the end date.

For February 29, test both jumping directly and updating period by period. From `2024-02-29`, `plusYears(4)` reaches `2028-02-29`; however, adding one year at a time loses day 29 on the step to 2025, and subsequent steps keep day 28. If the business rule requires restoring day 29 in the next leap year, you must preserve the original rule rather than only the adjusted date.

## 4. "Last Day of the Month" Is a Rule, Not a Fixed Day Number

There are two clear ways to get the last day of a month:

- When you already have a `LocalDate`: `date.with(TemporalAdjusters.lastDayOfMonth())`.
- When processing monthly periods: `yearMonth.atEndOfMonth()`.

`lastDayOfMonth()` inspects the month containing the input date, including February in a leap year. It does not advance the date into the next month. `YearMonth.atEndOfMonth()` fits well when the business data is "period 2024-02" and no specific day has been chosen yet. See [TemporalAdjusters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html) and [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

A common source of confusion lies in the next operation:

| Expression starting from `2024-02-29` | Result | Preserves month-end? |
| --- | --- | --- |
| `date.plusMonths(1)` | `2024-03-29` | No |
| `date.plusMonths(1).with(lastDayOfMonth())` | `2024-03-31` | Yes |
| `YearMonth.from(date).plusMonths(1).atEndOfMonth()` | `2024-03-31` | Yes |

Adding months does not remember "this date used to be the end of the month." If the requirement is month-end, represent or reapply that rule for each period.

A useful property for testing `lastDayOfMonth()` is idempotence: adjusting a date that is already at month-end again must keep the same value. Use `equals` to compare dates, not `==` to check object identity.

## 5. Two Algebraic Assumptions That Often Fail at Month Boundaries

### 5.1. Adding Month by Month Can Differ from Adding Multiple Months at Once

Starting from `2024-01-31`:

```text
Add 1 month:            2024-02-29
Add 1 more month:       2024-03-29

Add 2 months directly:  2024-03-31
```

The first step already clamped day 31 down to day 29. If you feed the resulting date into the next step, the information "the desired day is 31" is no longer present in that value.

Therefore, do not write tests asserting that `d.plusMonths(a).plusMonths(b)` always equals `d.plusMonths(a + b)`. That property does not hold for all dates.

### 5.2. Adding and Then Subtracting May Not Return to the Original Date

Again starting from `2024-01-31`:

```text
2024-01-31 + 1 month = 2024-02-29
2024-02-29 - 1 month = 2024-01-29
```

This is a consequence of losing the original day information when clamping to a shorter month. If you need to undo a business change, store the original date or enough rule data to reconstruct it; do not rely on month subtraction to reliably recover the old value.

## 6. Choosing a Policy for Monthly Recurring Schedules

Before choosing an API, state the policy in business terms.

| Policy | Appropriate calculation | What to test |
| --- | --- | --- |
| Always on the last day of the month | `YearMonth` for each period, then `atEndOfMonth()` | Months with 28, 29, 30, and 31 days |
| On day 31; use month-end for shorter months | Keep requested day as 31; take `min(31, target month length)` | After February, March must return to day 31 |
| On day 30; use month-end for shorter months | Keep requested day as 30; take `min(30, target month length)` | March must be day 30, not day 31 |
| Accept only the exact requested day | Check `YearMonth.isValidDay`, or let `atDay` throw and handle it | Must have a clear way to report/skip the period per requirements |

"Last day of the month" and "day 31, clamp if shorter" can produce the same results; "day 30, clamp if shorter" differs from both. Do not substitute one policy for another just because they coincide in a few test months.

For recurring schedules, keep two pieces of information: the anchor month of the schedule and the requested day-of-month. Each period is computed from the anchor month plus the period index, and then the policy is applied. Do not incrementally advance the clamped date from the previous period if the requirement needs to restore the original day.

For example, the "day 31, clamp if shorter" policy for the first three periods of 2024 yields 2024-01-31, 2024-02-29, and 2024-03-31. The "day 30, clamp if shorter" policy for February and March yields 2024-02-29 and 2024-03-30. The program below verifies both.

## 7. Java 17+ Program to Verify Results and Exceptions

Save the entire code below into a file named `MonthEndRules.java`. The program uses explicit checks and throws `AssertionError` on failure; it has no JUnit dependency and does not need the `-ea` flag. The `eq` and `rejects` helpers verify expected results and required `DateTimeException` throws, respectively.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Year;
import java.time.YearMonth;
import java.util.Objects;
import static java.time.temporal.TemporalAdjusters.lastDayOfMonth;

public class MonthEndRules {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static LocalDate d(String value) {
        return LocalDate.parse(value);
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (DateTimeException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected DateTimeException");
    }

    // Policy: keep the requested day, or use the target month's last day.
    private static LocalDate dueDate(YearMonth month, int requestedDay) {
        if (requestedDay < 1 || requestedDay > 31) {
            throw new IllegalArgumentException("requestedDay must be 1..31");
        }
        return month.atDay(Math.min(requestedDay, month.lengthOfMonth()));
    }

    public static void main(String[] args) {
        LocalDate anchor = d("2024-01-31");
        eq(d("2023-01-31").plusMonths(1), d("2023-02-28"));
        eq(anchor.plusMonths(1), d("2024-02-29"));
        eq(d("2024-03-31").minusMonths(1), d("2024-02-29"));
        eq(anchor.withMonth(2), d("2024-02-29"));
        eq(d("2024-02-29").withYear(2023), d("2023-02-28"));
        eq(d("2024-02-29").plusYears(1), d("2025-02-28"));
        eq(d("2024-02-29").plusYears(4), d("2028-02-29"));
        eq(anchor.plusDays(30), d("2024-03-01"));
        eq(d("2024-02-28").plusDays(1), d("2024-02-29"));
        eq(d("2023-02-28").plusDays(1), d("2023-03-01"));
        eq(d("2024-12-31").plusDays(1), d("2025-01-01"));

        eq(Year.isLeap(1900), false);
        eq(Year.isLeap(2000), true);
        eq(Year.isLeap(2100), false);
        eq(YearMonth.of(1900, 2).lengthOfMonth(), 28);
        eq(YearMonth.of(2000, 2).lengthOfMonth(), 29);
        eq(YearMonth.of(2100, 2).lengthOfMonth(), 28);

        rejects(() -> LocalDate.of(2023, 2, 29));
        rejects(() -> d("2024-02-15").withDayOfMonth(30));
        rejects(() -> YearMonth.of(2024, 2).atDay(31));
        rejects(() -> anchor.withMonth(13));

        LocalDate chained = anchor.plusMonths(1).plusMonths(1);
        LocalDate direct = anchor.plusMonths(2);
        eq(chained, d("2024-03-29"));
        eq(direct, d("2024-03-31"));
        eq(anchor.plusMonths(1).minusMonths(1), d("2024-01-29"));
        eq(anchor, d("2024-01-31"));

        LocalDate lastFebruary = d("2024-02-10").with(lastDayOfMonth());
        eq(lastFebruary, d("2024-02-29"));
        eq(lastFebruary.plusMonths(1), d("2024-03-29"));
        eq(lastFebruary.plusMonths(1).with(lastDayOfMonth()),
                d("2024-03-31"));
        eq(YearMonth.of(2024, 2).plusMonths(1).atEndOfMonth(),
                d("2024-03-31"));
        eq(dueDate(YearMonth.of(2024, 2), 30), d("2024-02-29"));
        eq(dueDate(YearMonth.of(2024, 3), 30), d("2024-03-30"));
        eq(dueDate(YearMonth.of(2023, 2), 31), d("2023-02-28"));

        // A 400-year Gregorian cycle contains 4,800 months.
        for (int year = 2000; year < 2400; year++) {
            for (int month = 1; month <= 12; month++) {
                YearMonth ym = YearMonth.of(year, month);
                LocalDate end = ym.atEndOfMonth();
                eq(end.getDayOfMonth(), ym.lengthOfMonth());
                eq(end.with(lastDayOfMonth()), end);
                eq(end.plusMonths(1).with(lastDayOfMonth()),
                        ym.plusMonths(1).atEndOfMonth());
            }
        }

        System.out.println("chained=" + chained);
        System.out.println("direct=" + direct);
        for (int i = 0; i < 3; i++) {
            YearMonth month = YearMonth.of(2024, 1).plusMonths(i);
            System.out.println(month + " due31=" + dueDate(month, 31));
        }
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 MonthEndRules.java
java MonthEndRules
```

Stdout:

```text
chained=2024-03-29
direct=2024-03-31
2024-01 due31=2024-01-31
2024-02 due31=2024-02-29
2024-03 due31=2024-03-31
PASS checks=14432
```

Read the output in three groups:

1. `chained` and `direct` demonstrate that adding months step by step can produce a different date from adding them directly.
2. The `due31` lines show that keeping the requested day separately restores day 31 after February.
3. The `PASS` line appears only after the normal cases, exception cases, and month-end properties all pass verification.

The loop iterates over 4,800 months in a 400-year cycle, from 2000 through 2399. For each month, it checks three properties: the day-of-month of the end date equals the month length; applying month-end adjustment again preserves the value; moving to the next month and adjusting to month-end matches the result built from `YearMonth`. There are 14,400 checks inside the loop and 32 individual checks, totaling 14,432.

These checks verify the selected behavior within the ISO calendar. They do not prove every business rule is correct, do not handle holiday calendars, and do not test the minimum/maximum bounds of the entire `LocalDate` domain.

## 8. Designing a Test Suite for Production Code

Choose data that is likely to expose bugs, rather than testing only a mid-month date.

| Data group | Suggested examples | Goal |
| --- | --- | --- |
| Mid-month date | Jan 15 to Feb 15 | Do not clamp the day when it is still valid |
| 31-day month to 30-day month | Mar 31 to April | Do not hardcode February as the only special case |
| Common/leap February | Feb 2023 and Feb 2024 | Distinguish 28 from 29 days |
| Century years | 1900, 2000, 2100 | Catch a naive "divisible by 4 is enough" formula |
| Both forward and backward | Jan 31 plus month, Mar 31 minus month | Test both adjustment directions |
| Year rollover | Dec 31 plus one day or one month | Test year transition |
| Invalid operations | 2023-02-29, day 30 in February | Verify the right exception type |
| Multi-period recurrence | Jan 31 → Feb → Mar | Catch loss of the requested day-of-month |
| Short month-end to longer month | 2024-02-29 → March | Catch confusing "add month" with "keep month-end" |

For each case, state the policy, input date, adjustment operation, and expected result before running. The expected result must come from the requirements; do not use the function under test to compute both the actual and expected results.

Properties such as "the result stays in the target month" or "the result is the exact last day of the month" complement fixed-date examples well. However, checking only "does not throw" is not enough: March 29 is still valid even when the required cutoff date is March 31.

## 9. Common Pitfalls and How to Fix Them

- **Ignoring the return value:** `LocalDate` is immutable. Calling `date.plusMonths(1)` and continuing to use the old variable does not update the date; store the result in a variable or return it.
- **Assuming every invalid day is clamped:** follow each method's exact contract. `withDayOfMonth(30)` in February throws an exception, unlike `withMonth(2)` from day 31.
- **Hardcoding 28 as the end of February:** use `YearMonth.lengthOfMonth()` or `atEndOfMonth()`.
- **Adding 30 days as a substitute for one month:** write the exact unit stated in the requirement; check the 2024-01-31 case to see the difference.
- **Using the previous period's result as the anchor when the original day must be kept:** store the requested day and compute each period from the anchor `YearMonth`.
- **Assuming a February 29 birthday/anniversary must always clamp to February 28:** Java has specific API behavior, whereas a business anniversary may be defined differently. Establish the policy first before implementing it.
- **Catching an exception and silently picking another date:** only fall back to the last day of the month when the policy allows it; otherwise, return an error or handle the invalid period explicitly.

## 10. Guided Practice

1. **Change the billing schedule requirement to day 30.** For February and March 2024, predict the results before calling `dueDate`. The correct results are `2024-02-29` and `2024-03-30`; if March yields day 29, the code is drifting from the previous period; if it yields day 31, the code is using the month-end policy.

2. **Add a case from 2024-03-31 to April.** `plusMonths(1)` gives `2024-04-30`. Adding one more month then gives `2024-05-30`, whereas adding two months directly from the original date gives `2024-05-31`.

3. **Predict the date after adding one year four times from 2024-02-29.** The final result is `2028-02-28`. Compare it with a single `plusYears(4)`, which gives `2028-02-29`; explain at which step information is lost.

4. **Change the policy to "throw an error if the month does not have the requested day."** Remove the `Math.min` step and use `month.atDay(requestedDay)`, or check `isValidDay` first. The February 2024 case with day 31 must be rejected; do not silently clamp the day.

Whenever you read or write a date adjustment, always identify both the API's rule and the business rule the adjustment is implementing. That is the basis for knowing whether to accept a clamped date, require month-end, or throw an error.
