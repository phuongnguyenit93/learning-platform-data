# Finding the Next or Previous Day of Week

## 1. Determining Whether to Include the Current Date

Suppose you need to find a Friday to close out a report. If today is Wednesday, "next Friday" is fairly clear. However, if today is already Friday, the requirement can have two meanings: pick today or pick next week's Friday. This difference determines the returned data, not just the naming.

`java.time.temporal.TemporalAdjusters` provides four corresponding adjusters: `next()`, `nextOrSame()`, `previous()`, and `previousOrSame()`. They accept a `DayOfWeek` and return a `TemporalAdjuster` rule; you apply the rule with `date.with(adjuster)`.

The before/after relationships and whether the base date is included are described in [Java SE 21 — TemporalAdjusters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html). With `LocalDate`, you can choose according to this table:

| Method | Condition on the resulting date relative to the base date | If the base date is already the target day | Days shifted |
| --- | --- | --- | --- |
| `next(dayOfWeek)` | After the base date | Advances 7 days | +1 to +7 |
| `nextOrSame(dayOfWeek)` | After or equal to the base date | Keeps that date | 0 to +6 |
| `previous(dayOfWeek)` | Before the base date | Moves back 7 days | -7 to -1 |
| `previousOrSame(dayOfWeek)` | Before or equal to the base date | Keeps that date | -6 to 0 |

The question to answer before writing code is: **should the starting point be included in the result?** Do not choose based on an assumption that the word "next" always includes or always excludes today in every business requirement.

## 2. Usage with `LocalDate`

An illustrative example inside a method:

```java
LocalDate date = LocalDate.of(2025, 6, 11);
LocalDate friday = date.with(TemporalAdjusters.next(DayOfWeek.FRIDAY));
```

`2025-06-11` is a Wednesday, so the result is `2025-06-13`. `LocalDate` is immutable; you must use the returned value. Calling `date.with(...)` and discarding the return value does not make `date` point to that Friday.

You can store a rule and reuse it multiple times:

```java
TemporalAdjuster nextFriday = TemporalAdjusters.next(DayOfWeek.FRIDAY);
LocalDate result = date.with(nextFriday);
```

The rule describes how to find the date rather than holding a fixed Friday. Applying the same `nextFriday` to different dates computes the result relative to each input date.

## 3. Understanding Distance in a Seven-Day Cycle

You do not need to write a loop incrementing day by day to use these APIs. However, understanding how the calculation works helps you spot off-by-one-week bugs.

According to [Java SE 21 — DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html), `getValue()` uses the ISO convention: Monday is 1, ..., Sunday is 7. Do not use `ordinal()` in place of this value.

Let `current` be the day-of-week number of the base date and `target` be the day-of-week number to find:

```text
Forward offset for nextOrSame = (target - current + 7) % 7
Backward offset for previousOrSame = (current - target + 7) % 7
```

If using the variants that exclude the base date (`next()` or `previous()`), a distance of 0 is replaced with 7. For example, from Wednesday (3) to Friday (5) is 2 days; from Friday to Friday is 0 days if keeping the same day is allowed, and 7 days if it must strictly move forward or backward.

The formulas only illustrate the weekly cycle. In application code, prefer the standard APIs so that the "before/after or same" semantics can be read directly from the method name. The month and year can change when adding/subtracting days; the result is not restricted to the input's month.

## 4. Complete Verification Program

Save the code to `NextPreviousWeekdayDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;

public class NextPreviousWeekdayDemo {
    private static void show(LocalDate date) {
        DayOfWeek target = DayOfWeek.FRIDAY;
        System.out.println("base = " + date + " " + date.getDayOfWeek());
        System.out.println("next Friday = "
                + date.with(TemporalAdjusters.next(target)));
        System.out.println("next or same = "
                + date.with(TemporalAdjusters.nextOrSame(target)));
        System.out.println("previous Friday = "
                + date.with(TemporalAdjusters.previous(target)));
        System.out.println("previous or same = "
                + date.with(TemporalAdjusters.previousOrSame(target)));
    }

    public static void main(String[] args) {
        show(LocalDate.of(2025, 6, 11));
        show(LocalDate.of(2025, 6, 13));

        LocalDate wednesday = LocalDate.of(2025, 6, 11);
        System.out.println("with Monday = "
                + wednesday.with(DayOfWeek.MONDAY));
        System.out.println("next Monday = "
                + wednesday.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("across year = " + LocalDate.of(2025, 12, 31)
                .with(TemporalAdjusters.next(DayOfWeek.MONDAY)));

        TemporalAdjuster nextFriday = TemporalAdjusters.next(DayOfWeek.FRIDAY);
        LocalDate occurrence = wednesday.with(nextFriday);
        for (int i = 1; i <= 4; i++) {
            System.out.println("occurrence " + i + " = " + occurrence);
            occurrence = occurrence.with(nextFriday);
        }

        LocalDateTime now = LocalDateTime.of(2025, 6, 13, 18, 0);
        LocalDate candidateDate = now.toLocalDate()
                .with(TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY));
        LocalDateTime candidate = candidateDate.atTime(LocalTime.of(17, 0));
        if (!candidate.isAfter(now)) {
            candidate = candidate.plusWeeks(1);
        }
        System.out.println("next Friday 17:00 = " + candidate);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NextPreviousWeekdayDemo.java
java NextPreviousWeekdayDemo
```

Output:

```text
base = 2025-06-11 WEDNESDAY
next Friday = 2025-06-13
next or same = 2025-06-13
previous Friday = 2025-06-06
previous or same = 2025-06-06
base = 2025-06-13 FRIDAY
next Friday = 2025-06-20
next or same = 2025-06-13
previous Friday = 2025-06-06
previous or same = 2025-06-13
with Monday = 2025-06-09
next Monday = 2025-06-16
across year = 2026-01-05
occurrence 1 = 2025-06-13
occurrence 2 = 2025-06-20
occurrence 3 = 2025-06-27
occurrence 4 = 2025-07-04
next Friday 17:00 = 2025-06-20T17:00
```

The program uses fixed dates so the output does not change depending on when it is run. The printed `WEDNESDAY` and `FRIDAY` are enum constant names, not formatted Vietnamese text.

## 5. Three Common Pitfalls

### Setting the day of week vs. finding a subsequent occurrence

`wednesday.with(DayOfWeek.MONDAY)` moves the date to Monday within the same ISO week, so from `2025-06-11` it returns `2025-06-09`. Meanwhile, `with(next(MONDAY))` must move forward, so it returns `2025-06-16`.

If the requirement is the upcoming Monday, do not just replace the `DayOfWeek` value and assume it always moves forward. Adjusting the day-of-week field within the same week and finding the next occurrence are two different questions.

### Finding the "nearest" occurrence does not always mean `previous()`

If the requirement is "the nearest Friday no later than the cutoff date," you must use `previousOrSame(FRIDAY)`. If the cutoff date is already Friday, the right result is that same date; `previous(FRIDAY)` would step back a week.

Conversely, if you need "the Friday immediately before the cutoff date, excluding the cutoff date," `previous(FRIDAY)` is the right choice. Words like "nearest" in business descriptions must be translated into explicit relationships: before, after, before or equal, after or equal. These four APIs do not automatically pick whichever date has the smallest absolute distance in both directions.

### The next day of week may be in another month or year

From `2025-12-31`, the next Monday is `2026-01-05`. You do not need to manually increment the month or handle year-end rollover. If the requirement adds a condition like "only within this month," you must check that condition after finding the date, or use another adjuster that expresses the month constraint. `next()` has no implicit month boundary.

## 6. Generating Multiple Recurring Dates and Ensuring Progress

In the program, applying `nextFriday` the first time to Wednesday yields June 13. After each print, applying `nextFriday` to the current result moves to the following Fridays: June 20, June 27, and then July 4.

If you replace the update step with `nextOrSame(FRIDAY)`, once `occurrence` is already a Friday, it will stay on the same date. A loop with a date-based termination condition might never reach its end date. Therefore:

- For the first occurrence, you can use `nextOrSame()` if you want to include the starting date.
- Once you have an occurrence, use `next()` or add one week for the subsequent step.
- In the backward direction, apply the same idea with `previous()` to guarantee the date decreases.

This only computes a list of dates. These APIs do not create a job scheduler, set timers, or manage task state.

## 7. A Matching Date Is Not Necessarily a Matching Time

The final part of the program considers the requirement "the next Friday at 17:00, which must be after the current timestamp." The current timestamp is fixed at Friday `2025-06-13` at 18:00. `nextOrSame(FRIDAY)` gives the current Friday, but combining it with 17:00 produces a time that has already passed.

Therefore, the program takes two steps:

1. Find a candidate date that may include today, then combine it with 17:00.
2. If the candidate is not after the current timestamp, add one week.

The condition `!candidate.isAfter(now)` also excludes the exact equality case, matching the "must be after" requirement. If the business rule allows running at the exact matching timestamp, the condition must be chosen accordingly.

This example uses `LocalDateTime`, so it expresses a rule in local date-time without a time zone. When you need an actual instant on the timeline, you must specify the zone/offset and how to handle days with offset transitions. You cannot assume that any two occurrences one calendar week apart are always exactly 168 hours apart in every time zone.

## 8. Limitations and Self-Checks

These adjusters only consider the day of the week. They have no awareness of public holidays, custom days off, or company closure schedules. The "next Friday" could fall on a holiday; if you need the "next business day," you must add the corresponding calendar and business rules.

Do not let `Locale` or calendar display conventions cause you to mix up day-of-week numbers. `DayOfWeek` always follows ISO values; to keep code readable, use `DayOfWeek.MONDAY` and `FRIDAY` instead of custom numeric conventions. Changing the display language does not change the next/previous behavior of the adjusters.

When testing a day-of-week finder function, include at least two cases: a base date on a different day from the target, and a base date already on the target day. Add a case that crosses a month or year boundary if the result is used for periodic reporting. These cases catch differences between the regular and `OrSame` variants much faster than testing only a mid-week date.

Exercise: given Sunday `2025-06-15`, find the next Monday and the previous Monday. The results are `2025-06-16` and `2025-06-09`, respectively. Then change the base date to Monday `2025-06-16`: `next(MONDAY)` must give the 23rd, whereas `nextOrSame(MONDAY)` keeps the 16th. Being able to explain this difference means you have properly determined whether to include the base date.
