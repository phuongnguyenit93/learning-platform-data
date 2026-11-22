# TemporalAdjuster and Rule-Based Transformations

## 1. From Adding an Amount to Finding a Date by a Rule

In date handling, some requirements specify a fixed amount: "add 7 days", "subtract 2 months". Other requirements describe a calendar target: "last day of the month", "next Monday", "the next day that does not fall on a weekend". The second kind of target needs an **adjustment rule**, not just a number.

`TemporalAdjuster` represents a rule that transforms a temporal object into a suitable result. You can name the rule, reuse it, and apply it via `with(adjuster)`.

Example:

```java
LocalDate date = LocalDate.of(2026, 10, 25);
LocalDate monthEnd = date.with(TemporalAdjusters.lastDayOfMonth());
```

`monthEnd` is `2026-10-31`; `date` remains `2026-10-25`. There is no need to write your own lookup table for the number of days in each month or manually check for leap years.

The snippet above illustrates usage inside a Java method; the standalone program with imports and full output is in section 7.

## 2. Three Roles to Distinguish

| Component | Role | Example |
|---|---|---|
| Date-time object | The value to which the rule is applied | `LocalDate`, `LocalDateTime` |
| `TemporalAdjuster` | Interface describing a rule | Rule to find the last day of the month |
| `TemporalAdjusters` | Utility class providing built-in rules and helper methods | `lastDayOfMonth()`, `next(...)`, `ofDateAdjuster(...)` |

`TemporalAdjuster` is a functional interface with a single abstract method:

```java
Temporal adjustInto(Temporal temporal);
```

This is an API signature, not a standalone program. `Temporal` represents a temporal object that can be adjusted using supported fields or units; it differs from `TemporalAccessor`, which focuses on reading temporal information.

The rule is separated from its call site, similar to encapsulating a processing strategy. The caller only needs to know "apply the last-day-of-month rule", rather than containing the entire algorithm for determining that date.

Not every `TemporalAdjuster` is meant exclusively for dates. There are objects and rules that adjust the time-of-day or offset portion. The scope of this lesson focuses on date rules in the ISO calendar.

## 3. Applying with `with` and Retaining the Return Value

There are two ways to call it at the API level:

```java
Temporal result = adjuster.adjustInto(temporal);
```

and the usually more readable form when the concrete date type is known:

```java
LocalDate result = date.with(adjuster);
```

`LocalDate.with(TemporalAdjuster)` returns `LocalDate`, so the caller does not need to cast from `Temporal`. Internally, the date-time object coordinates with the rule to produce the result.

With the immutable types in `java.time`, you must use the return value:

```java
date.with(TemporalAdjusters.lastDayOfMonth()); // Discards the result.
LocalDate end = date.with(TemporalAdjusters.lastDayOfMonth());
```

The first call does not update the `date` variable. Nor should you assume the result is always an object with a different memory address: the library may return an equivalent value when no change is needed. Focus on the date-time value, and use `equals` when comparing values.

The `TemporalAdjuster` contract requires not mutating the input object and returning an object of the same observable type. If you write a custom rule that accepts a `LocalDateTime` but directly returns a `LocalDate`, you have lost the type and the time portion instead of properly adjusting the input.

The interface does not automatically guarantee that every custom implementation is immutable. A rule must work safely when invoked concurrently; the easiest way to ensure this is to hold no mutable state, use no shared counters, and modify no external data while applying it.

## 4. Choosing Built-In Rules Before Writing Your Own

Some built-in groups in `TemporalAdjusters`:

| Rule | Meaning to read accurately |
|---|---|
| `firstDayOfMonth()` | Moves to the first day of the current month |
| `lastDayOfMonth()` | Moves to the last day of the current month |
| `firstDayOfNextMonth()` | Moves to the first day of the next month |
| `next(dayOfWeek)` | Finds the next occurrence after the current date, not keeping today |
| `nextOrSame(dayOfWeek)` | Keeps today if it is already the target day of week; otherwise finds the next occurrence |
| `previous(...)`, `previousOrSame(...)` | The corresponding rules in the backward direction |
| `firstInMonth(...)`, `lastInMonth(...)` | Finds the first/last occurrence of a day of week within the same month |

"Adjusting" does not necessarily move forward into the future. Moving to the first day of the month may go back several days; finding the next Monday may cross into the following month. You must read the meaning of the rule rather than inferring it from the fact that it is called via `with`.

If the current date is Monday, 26/10/2026:

```text
next(MONDAY)       -> 2026-11-02
nextOrSame(MONDAY) -> 2026-10-26
```

The two choices differ right at the boundary condition. In scheduling problems, you need to agree on whether "next Monday" includes today before choosing the API.

Adding an amount still has its own role. `plusDays(7)` always adds 7 days; `next(MONDAY)` adds a number of days depending on the input's day of week. Writing a rule to wrap a simple addition can be useful when it carries a domain name, but it does not change the semantics of that addition.

## 5. Creating a Custom Rule with `ofDateAdjuster`

If the natural algorithm is `LocalDate` → `LocalDate`, use `TemporalAdjusters.ofDateAdjuster(...)` to wrap it into a `TemporalAdjuster`.

Example rule for **the next day that is not Saturday or Sunday**:

1. Start from the day after the input, because "next" here does not include today.
2. If it is Saturday or Sunday, advance by one day.
3. Return the first day from Monday through Friday.

This is a simple weekday rule, **without considering holidays or an organization's work calendar**. Do not name or describe it as a full business calendar if that data is not present.

The lambda in `ofDateAdjuster` only processes `LocalDate`. The wrapper applies the resulting date back to the appropriate temporal object. Therefore, when used on `LocalDateTime` in the example, the date portion changes while the time 16:45 is preserved.

That does not mean every date-time type is compatible. A `LocalTime` has no date to apply this rule to. For non-ISO calendar systems or zoned types, you must determine the supported scope, required fields, and related policies; do not generalize from a `LocalDate` example to every `Temporal`.

If a rule uses an external holiday list, keep that data consistent during a single calculation, and define the calendar range and termination condition. Do not silently read "today" inside a rule that should depend solely on the input date.

## 6. Composition Order and Repeated Invocation Are Part of the Contract

Two rules are not necessarily commutative. With input 25/10/2026:

```text
End of month -> next Monday
2026-10-25 -> 2026-10-31 -> 2026-11-02

Next Monday -> end of month
2026-10-25 -> 2026-10-26 -> 2026-10-31
```

The results differ because the second rule sees the input already transformed by the first rule. If a feature wants "the last Monday of the month", choose the right rule such as `lastInMonth(MONDAY)`; do not replace it with the chain "end of month then next Monday".

You must also distinguish between a rule that keeps the same result when reapplied and a rule that keeps advancing:

- `lastDayOfMonth()` applied twice still yields the same last day of the month.
- "Next day that is not a weekend" applied twice will advance to one more valid day.

Do not assume every adjustment rule is idempotent—meaning calling it again does not change the result. This is especially important when the same value passes through multiple processing layers or when a task is retried.

## 7. Complete Runnable Program

Save the following code to `TemporalAdjusterDemo.java`. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;

public class TemporalAdjusterDemo {
    private static final TemporalAdjuster NEXT_WEEKDAY =
            TemporalAdjusters.ofDateAdjuster(date -> {
                LocalDate next = date.plusDays(1);
                while (next.getDayOfWeek() == DayOfWeek.SATURDAY
                        || next.getDayOfWeek() == DayOfWeek.SUNDAY) {
                    next = next.plusDays(1);
                }
                return next;
            });

    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2026, 10, 25);
        LocalDate monthEnd = original.with(TemporalAdjusters.lastDayOfMonth());
        System.out.println("original=" + original);
        System.out.println("monthEnd=" + monthEnd);
        System.out.println("originalAfter=" + original);

        LocalDate monday = LocalDate.of(2026, 10, 26);
        System.out.println("nextMonday="
                + monday.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("sameOrNextMonday="
                + monday.with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY)));

        System.out.println("monthEndThenMonday="
                + original.with(TemporalAdjusters.lastDayOfMonth())
                          .with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("mondayThenMonthEnd="
                + original.with(TemporalAdjusters.next(DayOfWeek.MONDAY))
                          .with(TemporalAdjusters.lastDayOfMonth()));

        LocalDate friday = LocalDate.of(2026, 10, 30);
        LocalDate next = friday.with(NEXT_WEEKDAY);
        System.out.println("nextWeekday=" + next);
        System.out.println("appliedAgain=" + next.with(NEXT_WEEKDAY));

        LocalDateTime appointment = friday.atTime(16, 45);
        System.out.println("adjustedDateTime=" + appointment.with(NEXT_WEEKDAY));

        LocalDate leapMonth = LocalDate.of(2024, 2, 10);
        System.out.println("leapMonthEnd="
                + leapMonth.with(TemporalAdjusters.lastDayOfMonth()));
    }
}
```

Compile and run:

```shell
javac TemporalAdjusterDemo.java
java TemporalAdjusterDemo
```

Expected output:

```text
original=2026-10-25
monthEnd=2026-10-31
originalAfter=2026-10-25
nextMonday=2026-11-02
sameOrNextMonday=2026-10-26
monthEndThenMonday=2026-11-02
mondayThenMonthEnd=2026-10-31
nextWeekday=2026-11-02
appliedAgain=2026-11-03
adjustedDateTime=2026-11-02T16:45
leapMonthEnd=2024-02-29
```

The outputs demonstrate the individual contracts:

- `originalAfter` proves the input variable is not updated by the preceding adjustment.
- The two Monday lines show the difference between "after today" and "today or after".
- The two chained-rule lines prove that order can change the result.
- The next day after Friday 30/10 is Monday 02/11 under the rule that only excludes weekends.
- Reapplying the next-weekday rule to Monday moves to Tuesday 03/11.
- `LocalDateTime` preserves its type and the time 16:45 after adjusting the date.
- February in a leap year has 29 as its last day of the month, without needing to write a leap-year branch manually.

## 8. Testing Rules with Boundary Conditions

When using or writing a custom `TemporalAdjuster`, clarify:

1. Which inputs are supported: ISO dates, date-times, or additional types?
2. Is the current date included if it already satisfies the condition?
3. Is the result allowed to cross into another month/year, or must it stay within the initial range?
4. Does applying it multiple times keep the result unchanged or keep shifting?
5. Does it depend on holidays, time zones, calendar systems, or external data?

For the `NEXT_WEEKDAY` example, testing Thursday, Friday, Saturday, Sunday, and the last day of the year helps confirm the exact "next" semantics. Extreme type boundaries such as `LocalDate.MAX` may have no subsequent day to construct; an operation exceeding the representable range throws an exception instead of wrapping around.

Do not replace an exception by arbitrarily returning the input date. If the rule cannot be fulfilled, an unchanged result may mislead the caller into thinking the condition was satisfied.

## 9. Practice on Your Own

Change the input of the custom rule to:

| Input date | Expected result of NEXT_WEEKDAY |
|---|---|
| `2026-10-29` (Thursday) | `2026-10-30` |
| `2026-10-31` (Saturday) | `2026-11-02` |
| `2026-11-01` (Sunday) | `2026-11-02` |
| `2026-11-02` (Monday) | `2026-11-03` |

Next, design a rule for "today if it is not a weekend, otherwise move to Monday". Point out the difference needed at the starting step compared to `NEXT_WEEKDAY`, and re-test the Monday input. The goal is to state the rule clearly before writing the algorithm, not just make a few sample dates pass.

References: [TemporalAdjuster](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjuster.html) and [TemporalAdjusters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html) in Java SE 21.
