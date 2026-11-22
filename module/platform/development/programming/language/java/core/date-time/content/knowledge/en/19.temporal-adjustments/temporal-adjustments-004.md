# Distinguishing next() from nextOrSame()

## 1. The difference lies in whether the current date is included

When the requirement is to “find the next Monday”, it is necessary to clarify: if today is already Monday, should we keep today or move to next week?

`TemporalAdjusters` provides two different adjusters:

- `next(dayOfWeek)`: finds the date with the requested day of week **after the input date**, always advancing by at least one day.
- `nextOrSame(dayOfWeek)`: keeps the input date if it already matches the day of week; otherwise, finds the closest matching date after it.

Given Monday, 2026-10-26:

```text
next(MONDAY)       -> 2026-11-02
nextOrSame(MONDAY) -> 2026-10-26
```

These are not two synonymous names. The “or same” condition determines the correct handling at the boundary of an appointment schedule, reporting period, or date range under consideration.

## 2. Create the adjuster and apply it with with

Both methods return a `TemporalAdjuster`. Apply the adjuster to a `LocalDate` via `with(...)`:

```java
LocalDate date = LocalDate.of(2026, 10, 26);
LocalDate next = date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
LocalDate sameOrNext = date.with(
        TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
```

`date` is not modified. You must use the returned result; calling `date.with(...)` and discarding the result does not update the variable. Built-in adjusters are immutable, so they can be kept as constants when reused multiple times.

`DayOfWeek` represents the exact day of the week. There is no need to use numbers like `0` or `1` and guess another API's numbering scheme. By `DayOfWeek` convention, Monday is 1 and Sunday is 7; the display locale choice does not change the meaning of `MONDAY`.

The snippet above is an example inside a Java method. The complete runnable program and required imports are in section 6.

## 3. If the input does not match the target day of week, both give the same result

With Monday as the target, consider the dates from 2026-10-26 to 2026-11-01:

| Input date | Day of week | next(MONDAY) | nextOrSame(MONDAY) |
|---|---|---|---|
| `2026-10-26` | Monday | `2026-11-02` | `2026-10-26` |
| `2026-10-27` | Tuesday | `2026-11-02` | `2026-11-02` |
| `2026-10-28` | Wednesday | `2026-11-02` | `2026-11-02` |
| `2026-10-29` | Thursday | `2026-11-02` | `2026-11-02` |
| `2026-10-30` | Friday | `2026-11-02` | `2026-11-02` |
| `2026-10-31` | Saturday | `2026-11-02` | `2026-11-02` |
| `2026-11-01` | Sunday | `2026-11-02` | `2026-11-02` |

Only the row whose input date matches the target day of week differs. If you only test with a date on a different day of the week, you might assume the two APIs always behave the same and miss the most important boundary bug.

In the ISO calendar, `next` shifts by 1 to 7 days; `nextOrSame` shifts by 0 to 6 days. Neither moves backward in date, and both can cross month or year boundaries.

### How to visualize the number of days shifted

Let `current` be the day-of-week number of the input date, and `target` be the target day-of-week number:

```text
delta = floorMod(target - current, 7)
```

`delta` is in 0–6. `nextOrSame` uses that exact distance; `next` replaces the 0 case with 7. This is a way to understand the mechanism for a seven-day week calendar, not a reason to reimplement the library in application code.

Therefore, `plusDays(7)` only matches `next(target)` when the input date already has the target day of week. If the input is Sunday and the target is Monday, `next(MONDAY)` only advances by one day.

## 4. Choose the API based on the requirement boundary

| Clarified requirement | Choice |
|---|---|
| The first day is Monday, including the start date | `nextOrSame(MONDAY)` |
| The next Monday occurrence after the current date | `next(MONDAY)` |
| Normalize a date to the nearest Monday ahead or itself | `nextOrSame(MONDAY)` |
| Generate the next occurrence after an event date that already occurred on Monday | `next(MONDAY)` |

Do not assume `nextOrSame` is better just because it handles one extra case. It can keep an old event date when the feature needs the next period. Conversely, `next` can skip a valid start date if the contract allows using that same day.

### Reapplying may differ

Given Monday, 2026-10-26:

```text
nextOrSame once:  2026-10-26
nextOrSame twice: 2026-10-26

next once:        2026-11-02
next twice:       2026-11-09
```

`nextOrSame` with the same target is idempotent in value: after the first call matches the day of week, subsequent calls keep it unchanged. `next`, on the other hand, advances to the following occurrence each time. Keep this in mind when multiple layers apply the adjuster or when processing is retried.

Do not use `==` to check whether a date “stays the same” in value. Use `equals`; what matters is the resulting date, not the object reference.

## 5. Adjusting the day of week alone is not enough to find an appointment after the current time

Suppose an appointment recurs every Monday at 09:00. If it is currently Monday at 10:00, `nextOrSame(MONDAY)` still keeps that same Monday. After setting the time to 09:00, the candidate ends up before the input timestamp.

On the other hand, if it is currently Monday at 08:00, using `next(MONDAY)` from the start would miss the 09:00 appointment on the same day, which has not happened yet.

A clear policy for this example is that **the appointment must be after the input timestamp, excluding that exact moment**:

1. Use `nextOrSame(MONDAY)` to produce the candidate date.
2. Set the candidate's time to 09:00.
3. If the candidate is not after the input, add one week.

When the input is exactly Monday at 09:00, the policy above moves to next week. If the feature should allow the exact current timestamp, the boundary condition must be updated accordingly; do not delegate that decision to the API name.

This example uses `LocalDateTime` within a single local-time context. It does not handle time zones, DST, or holidays. Adjusting the date of a zoned type also follows that type's rules; do not assume that shifting by one calendar day is always exactly 24 elapsed real hours.

## 6. Complete runnable program

Save the following snippet to `NextAndNextOrSameDemo.java`. The program requires Java 17 or later and needs no external libraries.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;

public class NextAndNextOrSameDemo {
    private static final TemporalAdjuster NEXT_MONDAY =
            TemporalAdjusters.next(DayOfWeek.MONDAY);
    private static final TemporalAdjuster MONDAY_OR_SAME =
            TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY);

    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2026, 10, 26);
        for (int i = 0; i < 7; i++) {
            LocalDate date = start.plusDays(i);
            System.out.println(date + " " + date.getDayOfWeek()
                    + " next=" + date.with(NEXT_MONDAY)
                    + " orSame=" + date.with(MONDAY_OR_SAME));
        }

        LocalDate once = start.with(MONDAY_OR_SAME);
        System.out.println("orSameTwice=" + once.with(MONDAY_OR_SAME));
        System.out.println("nextTwice="
                + start.with(NEXT_MONDAY).with(NEXT_MONDAY));
        System.out.println("original=" + start);

        LocalDateTime before = start.atTime(8, 0);
        LocalDateTime after = start.atTime(10, 0);
        LocalDateTime exactly = start.atTime(9, 0);
        System.out.println("before=" + nextMondayAtNine(before));
        System.out.println("after=" + nextMondayAtNine(after));
        System.out.println("exactly=" + nextMondayAtNine(exactly));
    }

    private static LocalDateTime nextMondayAtNine(LocalDateTime now) {
        LocalDateTime candidate = now.with(MONDAY_OR_SAME)
                .with(LocalTime.of(9, 0));
        if (!candidate.isAfter(now)) {
            candidate = candidate.plusWeeks(1);
        }
        return candidate;
    }
}
```

Compile and run:

```shell
javac NextAndNextOrSameDemo.java
java NextAndNextOrSameDemo
```

Expected output:

```text
2026-10-26 MONDAY next=2026-11-02 orSame=2026-10-26
2026-10-27 TUESDAY next=2026-11-02 orSame=2026-11-02
2026-10-28 WEDNESDAY next=2026-11-02 orSame=2026-11-02
2026-10-29 THURSDAY next=2026-11-02 orSame=2026-11-02
2026-10-30 FRIDAY next=2026-11-02 orSame=2026-11-02
2026-10-31 SATURDAY next=2026-11-02 orSame=2026-11-02
2026-11-01 SUNDAY next=2026-11-02 orSame=2026-11-02
orSameTwice=2026-10-26
nextTwice=2026-11-09
original=2026-10-26
before=2026-10-26T09:00
after=2026-11-02T09:00
exactly=2026-11-02T09:00
```

The loop covers the entire week, notably including an input date that matches the target day of week. The `before`, `after`, and `exactly` lines demonstrate that checking the time is a separate step after finding the candidate date. The `original` line shows that the adjusters do not mutate the original date.

## 7. Common pitfalls

- **Assuming `next` keeps today because today already matches the day of week:** `next` actively excludes the current date; use `nextOrSame` if you want to include it.
- **Using `nextOrSame` to generate every next period:** when the input is already the date of the previous period, the result may fail to advance.
- **Choosing `next` solely because an appointment must be in the future:** if today matches the day of week and the appointment time is still ahead, you may need to keep today and then compare times.
- **Replacing with `with(DayOfWeek.MONDAY)`:** this adjusts the day-of-week field with different semantics and can move backward within the week; it is not equivalent to finding the next Monday.
- **Assuming Monday is always a business day:** both APIs only consider the day of the week and have no knowledge of holidays or an organization's operating schedule.
- **Assuming the result must be in the same month:** finding the next day of week can cross into a new month and year; that is normal behavior.

The input and date-time type must support the required fields/units. Near the maximum limit of the type, if no valid date remains within the representable range, the adjustment throws an exception rather than wrapping around to the start of the calendar.

## 8. Practice

Change the target to `DayOfWeek.FRIDAY` and predict the results before running:

| Input | next(FRIDAY) | nextOrSame(FRIDAY) |
|---|---|---|
| `2026-10-29` (Thursday) | `2026-10-30` | `2026-10-30` |
| `2026-10-30` (Friday) | `2026-11-06` | `2026-10-30` |
| `2026-10-31` (Saturday) | `2026-11-06` | `2026-11-06` |

Then change the condition in `nextMondayAtNine` from `!candidate.isAfter(now)` to `candidate.isBefore(now)`. Explain why the 09:00 input changes its result, while the 08:00 and 10:00 inputs still follow the same date-selection behavior.

The deciding question when choosing between the two APIs is: **is the input date allowed to be the answer?** When the problem also involves an appointment time, follow up by answering whether the entire resulting date-time is allowed to equal the input.

Reference: [TemporalAdjusters — next and nextOrSame](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html) in Java SE 21.