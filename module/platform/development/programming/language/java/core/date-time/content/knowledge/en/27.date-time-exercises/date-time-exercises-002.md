# Calculating Age, Anniversaries, and Month-End Deadlines

## 1. The Practice Problem and Decisions to State Up Front

Three requirements sound familiar but involve different rules:

1. **Calculate completed age** as of a reference date.
2. **Find the next anniversary** starting from a given date.
3. **Determine a deadline at the end of a target month**.

Simply subtracting years or adding a fixed number of days does not solve these requirements correctly. You must handle leap years, dates not yet reached in the current year, and months of different lengths.

This exercise chooses the following contracts:

| Requirement | Policy used in this exercise |
| --- | --- |
| Age | Number of completed years based on the anniversary in the reference year |
| Future birth date | Reject |
| "Next" anniversary | Earliest occurrence **on or after** the reference date, inclusive of today |
| February 29 in a common year | Explicitly pass one of two policies: Feb 28 or Mar 1 |
| Month-end deadline | Select base month + months ahead, then take the last day of that month |
| Date-only deadline | The deadline date itself is still on time; only the day after is overdue |

The two Feb 29 policies are illustrative choices to make the design explicit. A real application must choose according to its own requirements, rather than adopting a method's default behavior as policy without checking.

The functions accept `LocalDate asOf` or `from` instead of calling a clock directly. The caller is responsible for determining the reference date in the business time zone. That makes the results testable with fixed dates.

## 2. Choosing Types for Each Piece of Data

| Information | Type |
| --- | --- |
| Full birth date | `LocalDate` |
| Reference date | `LocalDate` |
| Recurring annual anniversary pattern | `MonthDay` |
| Year for which to construct a specific occurrence | `Year` or a validated year number |
| Period for finding the month-end date | `YearMonth` |
| Days to wait until the next anniversary | `long` result from `ChronoUnit.DAYS.between` |

Do not use `MonthDay` in place of the full birth date when calculating age: it does not retain the birth year. Conversely, when only describing a recurring annual date pattern, `MonthDay` makes clear that no specific year has been chosen yet.

`LocalDate` represents a calendar date without time of day or time zone; all calculations in this exercise are date-based. See the model at [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 3. Calculating Completed Age with an Explicit Anniversary Policy

### 3.1. Why subtracting years is not enough

For someone born on May 10, 1990, as of May 9, 2024:

```text
Difference of year numbers: 2024 - 1990 = 34
Completed age:              33, because May 10 has not been reached yet
```

Only on May 10, 2024 does the age become 34.

An algorithm matching this exercise's contract:

1. Reject if the birth date is after the reference date.
2. Take the difference in years as the initial value.
3. Construct the anniversary in the reference year according to the chosen policy.
4. If the reference date is still before that anniversary, subtract one year.

Do not calculate age by dividing the number of days by 365 or 365.25. Anniversary-based age is a calendar rule, not an average duration.

### 3.2. A February 29 birth date needs an additional rule

With a birth date of February 29, 2000 and a reference date of February 28, 2023:

| Policy in a common year | Anniversary in 2023 | Completed age |
| --- | --- | --- |
| Use Feb 28 | `2023-02-28` | 23 |
| Use Mar 1 | `2023-03-01` | 22 |

By March 1, 2023, both yield 23. In the leap year 2024, the anniversary is February 29 under both policies; February 28 has not reached the anniversary yet.

An enum such as `LeapDayPolicy` makes this choice explicit at the call site. Do not hide the policy in an internal branch that callers are unaware of.

### 3.3. Period does not replace defining the policy

`Period.between(birthDate, asOf)` returns a calendar difference consisting of years, months, and days. `getYears()` retrieves the years component, not a statement of every age rule in an application.

From February 29, 2000 to February 28, 2023, the years component is 22. Meanwhile, this exercise's age function under the Feb 28 anniversary policy returns 23. The two results follow two different defined rules.

You can use `Period` when its calendar-difference contract matches your needs. There is no need to rewrite every calculation, but you must understand the result before calling it an age. See [Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html).

## 4. Sharing One Function to Build an Annual Occurrence

The `occurrence(monthDay, year, policy)` function in the program serves as a single shared point:

- For normal dates: combines month-day with the year.
- For February 29 in a leap year: returns February 29.
- For February 29 in a common year: chooses February 28 or March 1 according to the enum.

`Year.atMonthDay` automatically adjusts February 29 to February 28 in a common year. This exercise uses that behavior only for the Feb 28 policy branch; the Mar 1 branch is expressed separately.

By sharing this function, age calculation and anniversary reminders cannot accidentally apply two different policies. However, if two features genuinely have different requirements, they can intentionally pass different enum values.

The contract of month-day and attaching a year is described in [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

## 5. Finding the Next Anniversary, Inclusive of Today

The `nextOnOrAfter` function performs:

1. Construct the anniversary in the reference date's year.
2. If that date has not passed yet, return it immediately.
3. If it has passed, reconstruct the anniversary from the **original month-day** in the following year.

Example for a May 10 anniversary:

| Reference date | Result |
| --- | --- |
| `2024-05-09` | `2024-05-10` |
| `2024-05-10` | `2024-05-10` |
| `2024-05-11` | `2025-05-10` |

If the requirement is "the next occurrence after today" excluding the current date, the condition must be changed explicitly. Do not reuse an ambiguous name and leave callers to guess.

### Do not add one year to an already-adjusted date

With the original pattern Feb 29 and the Feb 28 policy, the 2023 occurrence is `2023-02-28`. If you take that date and call `plusYears(1)`, the result is `2024-02-28`—it does not restore day 29.

You must keep `MonthDay.of(2, 29)` and combine it with year 2024. Only then is the result properly `2024-02-29`.

That is why the algorithm keeps the original pattern rather than only the adjusted occurrence. Similarly, counting how many years have been celebrated requires the full start date; a standalone `MonthDay` is only enough to describe the recurring date pattern.

## 6. Calculating Month-End Deadlines with YearMonth

Contract of `endOfTargetMonth(base, monthsAhead)`:

- `monthsAhead = 0`: end of the month containing `base`.
- `monthsAhead = 1`: end of the next month.
- `monthsAhead = 2`: end of the month two months ahead.
- Negative values are rejected in this exercise.

The calculation is:

```text
Base LocalDate → Base YearMonth
               → add months
               → atEndOfMonth()
```

Examples:

| Base date | Months ahead | Deadline |
| --- | --- | --- |
| `2024-01-31` | 1 | `2024-02-29` |
| `2024-01-31` | 2 | `2024-03-31` |
| `2023-01-31` | 1 | `2023-02-28` |
| `2024-12-10` | 1 | `2025-01-31` |

Do not replace this with "add 30 days." Nor should you repeatedly add months to a clamped date and expect month-end to always be restored.

`YearMonth` models the monthly period accurately, and `atEndOfMonth` picks the last day for the target year-month. See [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

If the deadline falls on a weekend or holiday, this exercise still returns the exact month-end date. Shifting to another business day is an additional rule that must be specified separately, not silently added to the calculation.

## 7. Deadline Date vs. Expiration Instant

This exercise uses a `LocalDate` deadline and chooses the policy **still on time on the deadline date itself**:

```text
asOf before deadline → not overdue
asOf equal to deadline → not overdue
asOf after deadline  → overdue
```

Under this contract, the overdue condition is `asOf.isAfter(deadline)`.

If a system needs instant-level decisions—such as locking an action right at the start of the new day—it must add a time zone and an instant boundary. You can take the start of the day after the deadline as an exclusive upper bound in the specified zone. Do not assume `LocalDate` is UTC or append `23:59:59` as if that were always the end of the day.

The functions in this program do not handle cutoff times, holiday calendars, or time zones. They accept a reference date already determined by the caller.

## 8. Standalone Java 17+ Program

Save the following code as `CalendarBusinessPractice.java`. The program uses fixed data for reproducible results and requires no external libraries.

```java
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class CalendarBusinessPractice {
    public enum LeapDayPolicy { FEBRUARY_28, MARCH_1 }

    private static LocalDate d(String value) {
        return LocalDate.parse(value);
    }

    public static LocalDate occurrence(MonthDay day, int year,
                                       LeapDayPolicy policy) {
        Objects.requireNonNull(day, "day");
        Objects.requireNonNull(policy, "policy");
        Year target = Year.of(year);
        if (day.equals(MonthDay.of(2, 29)) && !target.isLeap()
                && policy == LeapDayPolicy.MARCH_1) {
            return LocalDate.of(year, 3, 1);
        }
        return target.atMonthDay(day);
    }

    public static int ageOn(LocalDate birthDate, LocalDate asOf,
                            LeapDayPolicy policy) {
        Objects.requireNonNull(birthDate, "birthDate");
        Objects.requireNonNull(asOf, "asOf");
        Objects.requireNonNull(policy, "policy");
        if (birthDate.isAfter(asOf)) {
            throw new IllegalArgumentException("birthDate must not be in the future");
        }
        int age = asOf.getYear() - birthDate.getYear();
        LocalDate anniversary = occurrence(MonthDay.from(birthDate),
                asOf.getYear(), policy);
        return asOf.isBefore(anniversary) ? age - 1 : age;
    }

    public static LocalDate nextOnOrAfter(MonthDay day, LocalDate from,
                                         LeapDayPolicy policy) {
        Objects.requireNonNull(from, "from");
        LocalDate candidate = occurrence(day, from.getYear(), policy);
        if (candidate.isBefore(from)) {
            return occurrence(day, from.getYear() + 1, policy);
        }
        return candidate;
    }

    public static LocalDate endOfTargetMonth(LocalDate base, long monthsAhead) {
        Objects.requireNonNull(base, "base");
        if (monthsAhead < 0) {
            throw new IllegalArgumentException("monthsAhead must be non-negative");
        }
        return YearMonth.from(base).plusMonths(monthsAhead).atEndOfMonth();
    }

    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        LeapDayPolicy feb28 = LeapDayPolicy.FEBRUARY_28;
        LeapDayPolicy mar1 = LeapDayPolicy.MARCH_1;
        LocalDate birth = d("1990-05-10");
        LocalDate asOf = d("2024-05-09");
        eq(ageOn(birth, asOf, feb28), 33);
        eq(ageOn(birth, d("2024-05-10"), feb28), 34);
        eq(ageOn(birth, d("2024-05-11"), feb28), 34);
        eq(ageOn(birth, birth, feb28), 0);
        rejects(() -> ageOn(d("2025-01-01"), asOf, feb28));

        LocalDate leapBirth = d("2000-02-29");
        eq(ageOn(leapBirth, d("2023-02-28"), feb28), 23);
        eq(ageOn(leapBirth, d("2023-02-28"), mar1), 22);
        eq(ageOn(leapBirth, d("2023-03-01"), feb28), 23);
        eq(ageOn(leapBirth, d("2023-03-01"), mar1), 23);
        eq(ageOn(leapBirth, d("2024-02-28"), feb28), 23);
        eq(ageOn(leapBirth, d("2024-02-29"), feb28), 24);
        eq(ageOn(leapBirth, d("2024-02-29"), mar1), 24);
        eq(Period.between(leapBirth, d("2023-02-28")).getYears(), 22);

        MonthDay birthday = MonthDay.from(birth);
        eq(nextOnOrAfter(birthday, asOf, feb28), d("2024-05-10"));
        eq(nextOnOrAfter(birthday, d("2024-05-10"), feb28), d("2024-05-10"));
        eq(nextOnOrAfter(birthday, d("2024-05-11"), feb28), d("2025-05-10"));
        MonthDay leapDay = MonthDay.of(2, 29);
        eq(nextOnOrAfter(leapDay, d("2023-02-28"), feb28), d("2023-02-28"));
        eq(nextOnOrAfter(leapDay, d("2023-02-28"), mar1), d("2023-03-01"));
        eq(nextOnOrAfter(leapDay, d("2023-03-01"), feb28), d("2024-02-29"));

        eq(endOfTargetMonth(asOf, 0), d("2024-05-31"));
        eq(endOfTargetMonth(d("2024-01-31"), 1), d("2024-02-29"));
        eq(endOfTargetMonth(d("2024-01-31"), 2), d("2024-03-31"));
        eq(endOfTargetMonth(d("2023-01-31"), 1), d("2023-02-28"));
        eq(endOfTargetMonth(d("2024-12-10"), 1), d("2025-01-31"));
        rejects(() -> endOfTargetMonth(asOf, -1));

        LocalDate nextBirthday = nextOnOrAfter(birthday, asOf, feb28);
        LocalDate deadline = endOfTargetMonth(asOf, 0);
        eq(ChronoUnit.DAYS.between(asOf, nextBirthday), 1L);
        eq(deadline.isAfter(deadline), false);
        eq(deadline.plusDays(1).isAfter(deadline), true);

        System.out.println("asOf=" + asOf);
        System.out.println("age=" + ageOn(birth, asOf, feb28));
        System.out.println("nextBirthday=" + nextBirthday);
        System.out.println("daysUntilBirthday=" + ChronoUnit.DAYS.between(asOf, nextBirthday));
        System.out.println("monthEndDeadline=" + deadline);
        System.out.println("leapAgeFeb28Policy=" + ageOn(leapBirth, d("2023-02-28"), feb28));
        System.out.println("leapAgeMarch1Policy=" + ageOn(leapBirth, d("2023-02-28"), mar1));
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CalendarBusinessPractice.java
java CalendarBusinessPractice
```

Stdout:

```text
asOf=2024-05-09
age=33
nextBirthday=2024-05-10
daysUntilBirthday=1
monthEndDeadline=2024-05-31
leapAgeFeb28Policy=23
leapAgeMarch1Policy=22
PASS checks=28
```

The `eq` helper actively throws `AssertionError` on mismatch, so the `-ea` flag is not required. The `rejects` helper verifies that inputs outside the contract are rejected.

The test suite covers:

- Before, on, and after a birthday.
- Age 0 on the birth date.
- Birth date in the future.
- February 29 birth date in a common year under both policies.
- Actual February 29 in a leap year.
- Anniversary inclusive of today and rolling into the next year.
- Restoring February 29 from the original pattern.
- End of February in common and leap years.
- Deadlines crossing a year boundary.
- Negative month offsets and overdue-day semantics.

The 2023/2024 values are simulated test data, not "the current date" at runtime.

## 9. Walking Through the Combined Scenario

For a person born `1990-05-10` and a reference date `2024-05-09`:

1. The initial year difference is 34.
2. The anniversary in the reference year is May 10, 2024.
3. The reference date is still before the anniversary, so completed age is 33.
4. The nearest anniversary on or after the reference date is still May 10, 2024.
5. The difference between the two `LocalDate` values is 1 day.
6. The monthly period of the reference date is 2024-05, so the month-end deadline is May 31, 2024.

Each step uses the type that matches its meaning. Do not format into strings and split year/month/day to compute. Format the results only at the output boundary when display is needed.

Returning age, next anniversary, and deadline separately gives each rule clear inputs. Do not bundle all three results into a single descriptive string and force another feature to parse it back out.

## 10. Common Pitfalls

| Pitfall | Incorrect outcome | How to avoid |
| --- | --- | --- |
| Only subtracting years | Age increases before the birthday arrives | Compare against the anniversary in the reference year |
| Dividing days by 365 | Does not follow anniversary dates | Use a calendar calculation matching the policy |
| No rule for Feb 29 | Two features return different ages | Pass an explicit policy |
| Assuming `Period.getYears` fits all cases | Differs from the Feb 28 policy in the example | Check the contract before using it |
| Adding years to an adjusted date | The next leap year stays on Feb 28 | Recombine from the original `MonthDay` |
| Adding 30 days for next month | Wrong for actual month lengths | Use `YearMonth.plusMonths` |
| Assuming month-end is always 31 | February and April do not have 31 days | Use `atEndOfMonth` |
| Not specifying whether today is included | Reminders jump to next year | State the inclusive/exclusive condition explicitly |
| Calling the clock in multiple places in one task | Reference date can shift across midnight | Pass a single determined `asOf` |

## 11. Extension Exercises with Expected Results

### Exercise 1: Age on both sides of a birthday

Someone born on December 20, 2000:

- On December 19, 2024: 23 years old.
- On December 20, 2024: 24 years old.
- On December 21, 2024: 24 years old.

Add these three cases without using the system date.

### Exercise 2: Anniversary strictly after the reference date

Write a function that returns only an occurrence **after** the reference date:

- For pattern May 10 and date May 10, 2024, the result must be May 10, 2025.
- For date May 9, 2024, the result is still May 10, 2024.

Change only the candidate-selection condition without losing the original month-day pattern.

### Exercise 3: Leap day and century years

For pattern February 29:

- Common year 2100: choose Feb 28 or Mar 1 depending on policy.
- Leap year 2000: keep Feb 29.

Do not use "divisible by 4" as the entire rule.

### Exercise 4: Sequence of month-end deadlines

Starting from base month 01/2024, generate the first three periods using month offsets 0, 1, 2:

```text
2024-01-31
2024-02-29
2024-03-31
```

Each period should be computed from the base month and the period index. Do not use the previous period's clamped date as the sole rule for the next period.

### Exercise 5: Holiday policy

Keep the month-end function unchanged. Design a separate step that adjusts the deadline according to a provided business calendar. State clearly whether shifting backward or forward is allowed, and whether that adjustment may cross into another month. Without a holiday calendar and rules, an alternative deadline cannot be asserted.

Correct calendar problems need more than an API that returns valid dates. They require properly typed inputs, consistent reference dates, and boundary policies expressed clearly in both code and test cases.
