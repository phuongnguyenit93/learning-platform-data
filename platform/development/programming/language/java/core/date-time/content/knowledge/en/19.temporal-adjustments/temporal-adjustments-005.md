# Finding a Specific Day of the Week in a Month

## From a Calendar Rule to a Specific Date

“The second Monday of the month” is a different rule from “the next Monday.” The first rule uses the **month** as its scope; the second rule uses the **current date** as its starting point for moving forward.

For example, with the source date `2024-02-18`:

- The first Monday of the month is `2024-02-05`.
- The second Monday of the month is `2024-02-12`.
- The next Monday after the source date is `2024-02-19`.

`TemporalAdjusters` helps express rules directly such as the first, last, or nth occurrence of a day of the week in a month. This article uses `LocalDate` with the ISO calendar and a seven-day week.

## 1. Choosing an Adjuster Based on the Requirement

| Requirement | Expression with source date `date` |
| --- | --- |
| First Monday in the month | `date.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY))` |
| Last Friday in the month | `date.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY))` |
| Second Monday in the month | `date.with(TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY))` |
| Last Monday in the month | `date.with(TemporalAdjusters.dayOfWeekInMonth(-1, DayOfWeek.MONDAY))` |
| Second-to-last Monday in the month | `date.with(TemporalAdjusters.dayOfWeekInMonth(-2, DayOfWeek.MONDAY))` |

`firstInMonth` and `lastInMonth` return the matching date within the month containing the source date. With `dayOfWeekInMonth`, a positive ordinal counts from the start of the month, and a negative ordinal counts from the end of the month. Special attention should be paid to the possibility of the result crossing the month boundary. [`TemporalAdjusters` Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)

`DayOfWeek` has seven constants:

```java
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
```

The snippet above lists the constant names, not a standalone program. In code, using `DayOfWeek.MONDAY` is usually clearer than a number. According to ISO, `DayOfWeek`'s `getValue()` is 1 for Monday through 7 for Sunday; do not use `ordinal()` to get the calendar day-of-week number. [`DayOfWeek` Documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html)

## 2. Visualizing How Occurrences Are Counted

February 2024 has the following Mondays:

```text
05/02       12/02       19/02       26/02
1st         2nd         3rd         4th
first                               last
                        second-to-last
```

Counting from the start:

```text
ordinal = 1 → 05/02
ordinal = 2 → 12/02
ordinal = 3 → 19/02
ordinal = 4 → 26/02
```

Counting from the end:

```text
ordinal = -1 → 26/02
ordinal = -2 → 19/02
ordinal = -3 → 12/02
ordinal = -4 → 05/02
```

The source date can be any date in the month. It does not have to precede the resulting date. Therefore, getting the first Monday from February 18 can move the result earlier than the source date.

## 3. Complete Program

Save as `WeekdayInMonthDemo.java`. The program uses Java 17 or later:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class WeekdayInMonthDemo {
    static Optional<LocalDate> nthWeekdayInMonth(
            YearMonth month, int occurrence, DayOfWeek weekday) {
        if (occurrence < 1 || occurrence > 5) {
            throw new IllegalArgumentException("Lan xuat hien phai trong 1..5");
        }

        LocalDate candidate = month.atDay(1).with(
                TemporalAdjusters.dayOfWeekInMonth(occurrence, weekday));

        if (!YearMonth.from(candidate).equals(month)) {
            return Optional.empty();
        }
        return Optional.of(candidate);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 18);
        YearMonth month = YearMonth.from(date);

        LocalDate firstMonday =
                date.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
        LocalDate secondMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY));
        LocalDate lastFriday =
                date.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY));
        LocalDate lastMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(-1, DayOfWeek.MONDAY));
        LocalDate secondLastMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(-2, DayOfWeek.MONDAY));

        System.out.println("original=" + date);
        System.out.println("firstMonday=" + firstMonday);
        System.out.println("secondMonday=" + secondMonday);
        System.out.println("lastFriday=" + lastFriday);
        System.out.println("lastMonday=" + lastMonday);
        System.out.println("secondLastMonday=" + secondLastMonday);

        LocalDate fifthMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(5, DayOfWeek.MONDAY));
        LocalDate zeroMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(0, DayOfWeek.MONDAY));

        System.out.println("rawFifthMonday=" + fifthMonday);
        System.out.println("zeroMonday=" + zeroMonday);

        System.out.println("checkedFifthMonday="
                + nthWeekdayInMonth(month, 5, DayOfWeek.MONDAY)
                        .map(LocalDate::toString)
                        .orElse("NONE"));
        System.out.println("checkedFifthThursday="
                + nthWeekdayInMonth(month, 5, DayOfWeek.THURSDAY)
                        .map(LocalDate::toString)
                        .orElse("NONE"));

        System.out.println("nextMondayFromOriginal="
                + date.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));

        List<LocalDate> mondays = new ArrayList<>();
        for (LocalDate current = firstMonday;
             YearMonth.from(current).equals(month);
             current = current.plusWeeks(1)) {
            mondays.add(current);
        }
        System.out.println("allMondays=" + mondays);

        System.out.println("addingOneMonth=" + secondMonday.plusMonths(1));
        LocalDate nextSecondMonday = month.plusMonths(1).atDay(1).with(
                TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY));
        System.out.println("recomputedNextMonth=" + nextSecondMonday);
    }
}
```

Compile and run:

```shell
javac --release 17 WeekdayInMonthDemo.java
java WeekdayInMonthDemo
```

Stdout:

```text
original=2024-02-18
firstMonday=2024-02-05
secondMonday=2024-02-12
lastFriday=2024-02-23
lastMonday=2024-02-26
secondLastMonday=2024-02-19
rawFifthMonday=2024-03-04
zeroMonday=2024-01-29
checkedFifthMonday=NONE
checkedFifthThursday=2024-02-29
nextMondayFromOriginal=2024-02-19
allMondays=[2024-02-05, 2024-02-12, 2024-02-19, 2024-02-26]
addingOneMonth=2024-03-12
recomputedNextMonth=2024-03-11
```

## 4. Key Point: `dayOfWeekInMonth` Can Go Outside the Month

The method name easily leads readers to think it always returns a date within the month. However, the counting algorithm can continue into another month.

In February 2024, there are only four Mondays. Requesting the fifth occurrence continues one week past the fourth, yielding `2024-03-04`, without automatically throwing an error because “this month lacks a fifth occurrence.”

Similarly, ordinal `0` has an API-defined meaning: the last matching day of the previous month. In the example, the result is `2024-01-29`. Negative numbers whose magnitude exceeds the number of occurrences in the month can also push the result back into the previous month.

`dayOfWeekInMonth` does not restrict the ordinal parameter to the range 1..5; it interprets the ordinal according to the week-counting algorithm. [`dayOfWeekInMonth` Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#dayOfWeekInMonth(int,java.time.DayOfWeek))

Therefore, for business requirements that **must exist within the selected month itself**, you need to verify the result again.

The `nthWeekdayInMonth` method in the program enforces a custom contract:

- Only accepts positive occurrences from 1 to 5.
- Computes the candidate using the library.
- Compares both the year and month of the candidate against the requested month.
- Returns `Optional.empty()` if that occurrence does not exist in the month.

The 1..5 limit is a choice of the application method, not a description of a parameter limit in the Java API.

Comparing `YearMonth` helps check the year as well when the result crosses the December 31 boundary. You should not compare only the month name or month number if the goal is to confirm the exact year-month period.

## 5. “Last” Does Not Mean “Fifth”

A day of the week can occur four or five times in a month. Therefore:

```java
date.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY));
```

is not equivalent to:

```java
date.with(TemporalAdjusters.dayOfWeekInMonth(5, DayOfWeek.FRIDAY));
```

These are two illustrative snippets using the existing `date`. In February 2024, the last Friday is 23/02, whereas the fifth occurrence moves into March.

If the requirement is “the last Friday,” use `lastInMonth` or ordinal `-1`. Only use the fifth occurrence when the business logic genuinely requires the fifth occurrence and already has a policy for months without one.

Possible policies include not scheduling that month, reporting no result, or requiring a different rule to be selected. Do not silently change “fifth occurrence” to “last occurrence” if the user has not chosen this rule.

## 6. How Counting From Month Boundaries Works

For a positive occurrence:

1. Find the first day of the month.
2. Find the first occurrence of the target day of the week.
3. Add `occurrence - 1` weeks.

For example, February 2024 starts on a Thursday. The first Monday is four days later, on 05/02. The second Monday is 05/02 plus one week, becoming 12/02.

Snippet illustrating an equivalent way to express the second occurrence:

```java
LocalDate firstMonday =
        month.atDay(1).with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
LocalDate secondMonday = firstMonday.plusWeeks(1);
```

For a negative occurrence, start from the last matching day of the month and step backward week by week.

Understanding the mechanism helps explain boundary-crossing cases, but in regular code you should prefer the method with the appropriate name. There is no need to rewrite day-of-week arithmetic manually if the library already expresses the requirement accurately.

If you calculate offsets manually using ISO day numbers, use `getValue()` and proper non-negative modulo arithmetic to avoid negative-number mistakes when wrapping from the end of the week to the start of the week. Using the enum and adjusters usually eliminates this kind of bug.

## 7. Distinguishing From `next`, `nextOrSame`, and “Changing the Day of the Week”

`firstInMonth(MONDAY)` uses the month as its scope. `next(MONDAY)` searches after the source date. These two operations are not interchangeable.

From 18/02/2024:

```text
firstInMonth(MONDAY) → 05/02/2024
next(MONDAY)         → 19/02/2024
```

If starting from a Monday itself, `next(MONDAY)` advances by one week; `nextOrSame(MONDAY)` can keep the same date. This difference is important when building a rule manually starting from the first day of the month.

You should also avoid using:

```java
date.with(DayOfWeek.MONDAY);
```

and assuming you have obtained the first Monday of the month. That adjusts the day-of-week field within the week of the source date, not an occurrence-in-month rule.

Read the requirement in two parts: **the target day of the week** and **the anchor/scope for searching**. If the scope is a month, express that month explicitly.

## 8. Monthly Recurring Schedules Must Recompute the Rule

The program outputs:

```text
Second Monday of February:   2024-02-12
Adding one month:            2024-03-12
Recomputing rule for March:  2024-03-11
```

March 12 is no longer the second Monday of March. `plusMonths(1)` adjusts by the number of months; it does not preserve a “day-of-week and occurrence” rule.

If a class schedule is held on the second Monday of every month:

```java
YearMonth nextMonth = month.plusMonths(1);
LocalDate nextMeeting = nextMonth.atDay(1).with(
        TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY));
```

This is an illustrative snippet using the imports from the complete program. Each month should be calculated from its corresponding `YearMonth` period and the same rule, rather than adding a month to the previous meeting date.

If the rule is the fifth occurrence, apply an existence-checking policy like the method in this article for each month.

## 9. When You Need All Dates With the Same Day of the Week in a Month

The program finds the first Monday and adds one week at a time until it leaves the month. The resulting list is:

```text
2024-02-05
2024-02-12
2024-02-19
2024-02-26
```

The stopping condition checking `YearMonth.from(current).equals(month)` ensures 04/03 is not included in the February schedule.

This approach fits when the UI needs to display all class dates for a given day of the week. If you only need the first, last, or nth occurrence, calling an adjuster directly is usually clearer than building the entire list and picking an element.

## 10. Notes When Applying to Business Logic

- `LocalDate` is immutable; you must keep the return value from `with`.
- A Friday in a month is not automatically a working day if it falls on a separate holiday schedule.
- The result is a date, without a time or time zone to identify a global instant.
- If the requirement is a schedule for a specific month, `YearMonth` expresses the input more clearly than an arbitrary date.
- “The second occurrence of Monday” does not mean “week 2” under every week-numbering rule; here it only counts occurrences of the same day of the week within the month.

Before using the result, validate meaningful conditions: whether the day of the week is right, whether the year-month is right, whether the occurrence number is right, and whether the policy for a missing fifth occurrence is enforced.

Useful test cases include a month starting right on the target day of the week, a month with only four occurrences, a month with five occurrences, a leap/non-leap February, and December when the candidate crosses into the next year. Do not test only a month where the target day of the week happens to occur five times.

## 11. Self-Practice

1. From any date in a month, which method gets the last Wednesday of the month?
2. Why can the fifth Monday of February 2024 yield March 4?
3. To be sure the result belongs to the exact target month period, what should you compare?
4. Does adding one month to the second Monday preserve that rule?
5. Is ordinal `0` in `dayOfWeekInMonth` automatically rejected?

Suggested answers:

1. `date.with(TemporalAdjusters.lastInMonth(DayOfWeek.WEDNESDAY))`.
2. The algorithm continues counting weeks; the API does not treat a missing fifth occurrence as an error.
3. Compare both year and month, for example using `YearMonth`.
4. No; you must recompute from the target month.
5. No; it means the last matching day of the previous month.

Choose the adjuster matching the exact calendar rule, check month boundaries when counting occurrences, and recompute the rule for each period when generating recurring schedules.
