# plusYears() from a Leap Day and Adjustment Rules in Java

## Objective

The `plusYears(long years)` method adds a number of calendar years to a date or date-time. The key rule is that **the result must be a valid date in the target month**. When the corresponding day of the month does not exist, Java adjusts to the last valid day of that month instead of keeping an invalid date or automatically rolling over into the next month.

A classic example is February 29: adding one year to this date produces February 28 in a non-leap year. This rule can easily cause surprises when calculating ages, anniversaries, due dates, contract renewals, or when chaining multiple year additions.

The examples below use Java 17+ and the `java.time` API.

## 1. plusYears() Operates on Calendar Years

With `LocalDate`, the call:

```java
LocalDate nextYear = date.plusYears(1);
```

does not mean adding exactly 365 days or 365 × 24 hours. It preserves the month and day if possible, adds to the year component, and then adjusts the day if the target month does not have that day. A leap year can have 366 days; the elapsed duration between two calendar points is therefore not always equal.

For an ordinary date, the result keeps the same month and day:

```java
LocalDate date = LocalDate.of(2023, 5, 12);
System.out.println(date.plusYears(1));
```

Output:

```text
2024-05-12
```

For a leap day, the expected month and day may not be valid in the target year:

```java
LocalDate leapDay = LocalDate.of(2020, 2, 29);
System.out.println(leapDay.plusYears(1));
```

Output:

```text
2021-02-28
```

The year 2021 is not a leap year, so February only has 28 days. Java chooses the last valid day of February. It does **not** produce `2021-03-01`, nor does it throw an error just because February 29 does not exist in the target year.

## 2. Invalid Date Adjustment Rules

Conceptually, adding years to a calendar date performs the following steps:

1. Compute the target year by adding `years` to the current year.
2. Keep the current month and day as the candidate date in the target year.
3. If that year–month–day combination is invalid, replace the day with the last valid day of the target month.

Example table:

| Initial Date | Call | Result | Reason |
|---|---|---|---|
| `2020-02-29` | `plusYears(1)` | `2021-02-28` | Target year is not a leap year; February 29 does not exist. |
| `2020-02-29` | `plusYears(4)` | `2024-02-29` | 2024 is a leap year; the day can be preserved. |
| `2021-01-31` | `plusMonths(1)` | `2021-02-28` | The same rule applies to adding months. |
| `2020-02-29` | `plusYears(0)` | `2020-02-29` | No adjustment is needed when the target date remains valid. |

Leap years in the ISO calendar used by `LocalDate` are determined by the Gregorian rule: a year divisible by 4 is a leap year, except years divisible by 100, which must also be divisible by 400 to be a leap year. Therefore, 2000 is a leap year but 1900 is not; 2024 is a leap year while 2023 and 2100 are not.

You do not need to write your own leap-year check logic to use `plusYears()`. The date-time API handles date validity according to the ISO calendar, avoiding bugs from manually calculating the number of days in a month.

## 3. One Addition of Four Years Differs from Four Additions of One Year

An important point: `plusYears(4)` calculates directly from the original date to the target year. If split into multiple steps, each step adjusts the date, and the adjusted result becomes the input for the next step.

```java
LocalDate original = LocalDate.of(2020, 2, 29);

LocalDate direct = original.plusYears(4);

LocalDate stepped = original;
for (int i = 0; i < 4; i++) {
    stepped = stepped.plusYears(1);
}

System.out.println("Original: " + original);
System.out.println("Direct:   " + direct);
System.out.println("Stepped:  " + stepped);
```

Output:

```text
Original: 2020-02-29
Direct:   2024-02-29
Stepped:  2024-02-28
```

Step-by-step progression of the cumulative addition:

| Step | Calculation | Result |
|---|---|---|
| 0 | Original date | `2020-02-29` |
| 1 | `2020-02-29.plusYears(1)` | `2021-02-28` |
| 2 | `2021-02-28.plusYears(1)` | `2022-02-28` |
| 3 | `2022-02-28.plusYears(1)` | `2023-02-28` |
| 4 | `2023-02-28.plusYears(1)` | `2024-02-28` |

In the first step, day 29 was adjusted to day 28. Subsequent additions keep day 28 because the object no longer retains that the original date was February 29. When you need the corresponding date four years after the original anchor date, call `original.plusYears(4)`. When business logic requires successive annual periods starting from the actual adjusted date of the previous period, looping `plusYears(1)` may be more accurate. Choose based on business semantics, not just loop style.

## 4. Full Example: Leap-Day Adjustment

Create the file `LeapDayPlusYearsDemo.java`:

```java
import java.time.LocalDate;

public class LeapDayPlusYearsDemo {
    public static void main(String[] args) {
        LocalDate leapDay = LocalDate.of(2020, 2, 29);

        LocalDate oneYearLater = leapDay.plusYears(1);
        LocalDate fourYearsLater = leapDay.plusYears(4);

        LocalDate cumulative = leapDay;
        for (int i = 0; i < 4; i++) {
            cumulative = cumulative.plusYears(1);
        }

        System.out.println("Start:       " + leapDay);
        System.out.println("Plus 1 year: " + oneYearLater);
        System.out.println("Plus 4 years:" + fourYearsLater);
        System.out.println("Cumulative:  " + cumulative);
    }
}
```

Compile and run:

```bash
javac LeapDayPlusYearsDemo.java
java LeapDayPlusYearsDemo
```

Output:

```text
Start:       2020-02-29
Plus 1 year: 2021-02-28
Plus 4 years:2024-02-29
Cumulative:  2024-02-28
```

The spacing in the output is part of the string passed to `println`: the `Plus 4 years:` line has no trailing space, so the date prints immediately after the colon. If you want better readability, add a space after the colon in the print statement.

## 5. plusYears() Does Not Mutate the Original Object

`java.time` types such as `LocalDate`, `LocalDateTime`, and `ZonedDateTime` are immutable. The `plusYears()` method returns a new object; it does not modify the receiver object.

```java
LocalDate original = LocalDate.of(2020, 2, 29);
LocalDate adjusted = original.plusYears(1);

System.out.println(original);
System.out.println(adjusted);
```

Output:

```text
2020-02-29
2021-02-28
```

A common mistake is calling `date.plusYears(1)` without storing the result, expecting `date` to change on its own. You must assign the result back if you want the current reference variable to point to the new value:

```java
date = date.plusYears(1);
```

Reassigning a reference variable does not mutate the old object; it only updates the variable's value to point to the new object.

## 6. LocalDateTime: Date Is Adjusted, Time Is Preserved

For `LocalDateTime`, the date adjustment rule is the same as `LocalDate`; the hour, minute, second, and nanosecond components remain unchanged.

```java
LocalDateTime meeting =
        LocalDateTime.of(2020, 2, 29, 9, 45, 30);

System.out.println(meeting.plusYears(1));
```

Output:

```text
2021-02-28T09:45:30
```

Here there is no time zone, offset, or UTC instant attached to the object. `LocalDateTime.plusYears(1)` operates on a local calendar; it cannot on its own determine DST effects or convert to an absolute instant.

If the application is scheduling an event at "09:45 local time", store or handle the time zone separately as needed. Do not assume that `LocalDateTime` is a global timestamp just because it contains both date and time.

## 7. ZonedDateTime: Zoned Calendar Year Addition

`ZonedDateTime.plusYears()` also applies calendar year addition and invalid date adjustment. However, `ZonedDateTime` has a `ZoneId` and an offset; if the time-zone rules at the new point in time differ, the local time and offset must be resolved according to the zone rules.

Leap-day example in a time zone:

```java
ZonedDateTime start = ZonedDateTime.of(
        2020, 2, 29, 9, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime nextYear = start.plusYears(1);
System.out.println(nextYear);
```

On the target date February 28, 2021, the local time 09:00 is still valid and is preserved. The offset is calculated according to `Europe/Paris` rules for the target date; you should not hard-code the 2020 offset for all subsequent years.

Adding one calendar year to `ZonedDateTime` is not equivalent to adding a fixed number of seconds. If the business requirement is "after exactly 365 × 24 hours", compute using a duration such as `Duration`. If the requirement is "the same date and local time next year", use calendar arithmetic like `plusYears(1)` and define a policy for adjusted dates.

## 8. When Is Adjusting February 29 Right for Business Logic?

There is no single leap-day policy that fits every system. `plusYears()` provides consistent behavior: adjusting to the last day of the month when the original day does not exist in the target month. However, the application should determine whether that matches the business rules.

| Business Scenario | Question to Clarify | Approach |
|---|---|---|
| Birthday/anniversary of someone born on Feb 29 | Celebrate on Feb 28 or Mar 1 in a non-leap year? | Define the policy by product/legal rules; do not let the API default decide business meaning. |
| Contract renewal by calendar date | What date does the due date fall on if Feb 29 does not exist? | Explicitly document date-adjustment terms; test month-end dates. |
| Calculation cycle from an anchor date | Do you need the point after N years directly or a chain of yearly points? | Use `original.plusYears(n)` for points from the anchor; use cumulative addition when each period starts from the previous one. |
| Annual reminder schedule in local time | Must the local time and time zone be preserved? | Use an appropriate calendar type, typically local date/time with `ZoneId`, and define DST rules. |

If the business requires March 1 in non-leap years for a February 29 date, `plusYears()` does not directly express that policy. You need to write your own business rule and test it explicitly; do not assume the API will automatically roll over to March 1.

## 9. Testing Leap-Day Rules

Tests that should be included in an application handling calendar dates:

- February 29 of a leap year plus 1 year into a non-leap year.
- February 29 plus 4 years to the next leap year.
- Century-year cases such as 1900 and 2000 under the ISO calendar.
- Adding one year multiple times versus adding N years once.
- Other month-end dates such as January 31 when adding months, if the system also uses `plusMonths()`.
- `LocalDateTime` and `ZonedDateTime` to verify local time/time zone are handled as expected.

Simple assertion-based test example:

```java
import java.time.LocalDate;

public class LeapDayAssertions {
    public static void main(String[] args) {
        LocalDate leapDay = LocalDate.of(2020, 2, 29);

        if (!leapDay.plusYears(1).equals(LocalDate.of(2021, 2, 28))) {
            throw new AssertionError("Year adjustment failed");
        }

        if (!leapDay.plusYears(4).equals(LocalDate.of(2024, 2, 29))) {
            throw new AssertionError("Leap year restoration failed");
        }

        System.out.println("All checks passed");
    }
}
```

Compile and run:

```bash
javac LeapDayAssertions.java
java LeapDayAssertions
```

Output when all checks pass:

```text
All checks passed
```

These assertions do not depend on the system time zone because they only use `LocalDate`. For logic based on `ZonedDateTime`, pass an explicit `ZoneId` instead of relying on the machine's default configuration so test results are reproducible.

## 10. Common Pitfalls

1. **Assuming adding one year equals 365 days.** A calendar year can have 365 or 366 days; use `plusYears()` for calendar-year arithmetic.
2. **Thinking `plusYears()` will always preserve the day of the month.** A non-existent target day is adjusted to the last day of the month.
3. **Adding cumulatively while expecting results relative to the original date.** A date already adjusted to February 28 will remain day 28 when adding years step by step. Keep the original anchor date if each milestone must be computed independently.
4. **Forgetting to assign the result.** `java.time` classes are immutable; the result must be captured in a variable.
5. **Handling leap years manually with a fixed number of days.** Use `LocalDate` and calendar arithmetic to leverage the built-in standard rules.
6. **Using LocalDateTime as an absolute point in time.** This type has no offset or zone; for global events, use `Instant` or an appropriate type carrying an offset/zone.
7. **Not aligning on a policy for February 29 anniversaries.** Technical rules can determine a valid date, but the business decision must be specified separately.

## 11. Self-Check

**Question 1.** What date does `LocalDate.of(2020, 2, 29).plusYears(1)` return?

**Answer:** `2021-02-28`, because 2021 does not have February 29 and Java adjusts to the last day of the month.

**Question 2.** Why does `2020-02-29.plusYears(4)` (computed directly from the original date) differ from calling `plusYears(1)` four times?

**Answer:** Computing directly to 2024 preserves February 29 because 2024 is a leap year. When adding one year at a time, the first step changes the date to February 28; subsequent steps continue using day 28.

**Question 3.** Does `plusYears(1)` add exactly 365 × 24 hours?

**Answer:** No. It is a calendar calculation; the actual number of days and duration depend on the year span, as well as the time zone if using `ZonedDateTime`.

**Question 4.** Does `date.plusYears(1)` modify the `date` object?

**Answer:** No. It returns a new object. You need to write `date = date.plusYears(1)` if you want the variable to point to the result.

**Question 5.** If a business rule states that someone born on February 29 celebrates their birthday on March 1 in non-leap years, should you rely solely on `plusYears()`?

**Answer:** No. By default, `plusYears()` adjusts to February 28. The March 1 rule must be explicitly implemented according to the business requirements.

---

**Takeaway:** `plusYears()` performs calendar addition and automatically adjusts invalid dates to the end of the month. For leap days, distinguish between milestones computed directly from the original date and cumulative period-by-period additions, and verify that the February 29 policy matches your business requirements.