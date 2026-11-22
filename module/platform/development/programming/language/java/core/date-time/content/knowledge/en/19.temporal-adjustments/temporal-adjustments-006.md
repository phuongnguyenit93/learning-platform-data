# Creating a `TemporalAdjuster` with `ofDateAdjuster()`

## 1. Encapsulating a Date Adjustment Rule

An application may repeatedly need rules such as “move to the next working day”, “shift the cutoff date according to an internal calendar”, or “add two calendar days”. If the rule depends only on the date, duplicating the branching logic at every call site makes it harder to test and can easily lead to inconsistent interpretations.

`TemporalAdjusters.ofDateAdjuster()` turns a function that takes a `LocalDate` and returns a `LocalDate` into a `TemporalAdjuster`. The resulting adjuster can then be used through the familiar `date.with(adjuster)` syntax.

According to [Java SE 21 — ofDateAdjuster()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#ofDateAdjuster(java.util.function.UnaryOperator)), this method lets you write date-based rules without manually implementing the low-level `Temporal` interface. It does not supply a holiday calendar or business logic of its own; the function passed in by the application determines how the adjustment is performed.

If a built-in rule already exists—such as the end of the month or the next Friday—use the corresponding standard adjuster. If you only need to add two days in a single place, `date.plusDays(2)` is already clear. `ofDateAdjuster()` is useful when you want to name, reuse, or pass a date-based rule across different parts of the codebase.

## 2. How Is a `LocalDate → LocalDate` Function Wrapped?

The accepted function type is `UnaryOperator<LocalDate>`: both the input and output are `LocalDate`. A simple lambda can be written as:

```java
// Illustrated inside a method.
TemporalAdjuster twoDaysLater =
        TemporalAdjusters.ofDateAdjuster(date -> date.plusDays(2));
LocalDate result = LocalDate.of(2025, 6, 13).with(twoDaysLater);
```

The result is `2025-06-15`. The lambda does not mutate the input date because `LocalDate` is immutable; it must return the resulting date.

You can think of the wrapping mechanism in three steps:

```text
Input Temporal
      ↓ extract the LocalDate part
application-supplied LocalDate → LocalDate function
      ↓ adjusted date
apply that date back onto the original Temporal
```

Therefore, when applied to a `LocalDateTime`, the rule still operates only on the date and does not read the time of day. The wrapper ensures that the returned object has a type matching the input rather than forcing every result to be a `LocalDate`.

[Java SE 21 — TemporalAdjuster](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjuster.html) specifies that an adjustment does not mutate the input and returns an object of the same observable type. The `temporal.with(adjuster)` syntax is usually clearer than calling `adjuster.adjustInto(temporal)` directly.

## 3. Defining the Working-Day Rule in the Example

We will build a rule with the following contract:

1. Find a date **after** the input date, excluding the input date itself.
2. Saturday and Sunday are treated as weekend days off in this example.
3. Dates in the `holidays` set must not be selected either.
4. The rule uses a snapshot of the holiday set taken at creation time.

The date `2025-06-16` is marked as a holiday solely for testing. This is hypothetical sample data for the lesson, not a statement about an official holiday schedule. In practice, an application must load a calendar appropriate for the organization and the date range being processed.

The requirement “after the input date” directly affects the algorithm: it must advance by one day at least once before checking. Even if the input date is already a working day, the result must still move forward to the next working day.

## 4. Complete Runnable Program

Save the following code to `OfDateAdjusterDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;
import java.util.HashSet;
import java.util.Set;

public class OfDateAdjusterDemo {
    private static TemporalAdjuster nextWorkingDay(Set<LocalDate> holidays) {
        Set<LocalDate> snapshot = Set.copyOf(holidays);
        return TemporalAdjusters.ofDateAdjuster(date -> {
            LocalDate candidate = date;
            do {
                candidate = candidate.plusDays(1);
            } while (candidate.getDayOfWeek() == DayOfWeek.SATURDAY
                    || candidate.getDayOfWeek() == DayOfWeek.SUNDAY
                    || snapshot.contains(candidate));
            return candidate;
        });
    }

    public static void main(String[] args) {
        Set<LocalDate> source = new HashSet<>();
        source.add(LocalDate.of(2025, 6, 16));
        TemporalAdjuster nextWorking = nextWorkingDay(source);

        LocalDate[] dates = {
            LocalDate.of(2025, 6, 13),
            LocalDate.of(2025, 6, 14),
            LocalDate.of(2025, 6, 15),
            LocalDate.of(2025, 6, 17)
        };
        for (LocalDate date : dates) {
            System.out.println(date + " -> " + date.with(nextWorking));
        }

        source.add(LocalDate.of(2025, 6, 17));
        LocalDate original = LocalDate.of(2025, 6, 13);
        System.out.println("snapshot result = " + original.with(nextWorking));
        System.out.println("original = " + original);

        LocalDateTime meeting = original.atTime(15, 30);
        System.out.println("date-time = " + meeting.with(nextWorking));
        ZonedDateTime zoned = meeting.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("zoned = " + zoned.with(nextWorking));

        try {
            YearMonth.of(2025, 6).with(nextWorking);
        } catch (DateTimeException ex) {
            System.out.println("YearMonth = DateTimeException");
        }

        TemporalAdjuster twoDaysLater =
                TemporalAdjusters.ofDateAdjuster(date -> date.plusDays(2));
        System.out.println("simple rule = " + original.with(twoDaysLater));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 OfDateAdjusterDemo.java
java OfDateAdjusterDemo
```

Output:

```text
2025-06-13 -> 2025-06-17
2025-06-14 -> 2025-06-17
2025-06-15 -> 2025-06-17
2025-06-17 -> 2025-06-18
snapshot result = 2025-06-17
original = 2025-06-13
date-time = 2025-06-17T15:30
zoned = 2025-06-17T15:30+07:00[Asia/Ho_Chi_Minh]
YearMonth = DateTimeException
simple rule = 2025-06-15
```

## 5. Reading the Algorithm and Output

### Always Advance Before Checking

The factory method `nextWorkingDay()` returns an adjuster; it does not compute a date at the moment it is called. Each time a date object invokes `.with(nextWorking)`, the lambda receives that date and begins the calculation.

`candidate` starts as the input date. The `do ... while` loop advances the date first, then rejects it if it falls on Saturday, Sunday, or in the holiday set. All intermediate variables belong strictly to that single invocation.

Starting from Friday `2025-06-13`, the rule skips Saturday the 14th, Sunday the 15th, and Monday the 16th (marked as a holiday), so it picks Tuesday the 17th. Starting from Tuesday the 17th, the result is Wednesday the 18th because the original date is excluded from the eligible set.

If the contract changes to “the first working day from the reference date, inclusive of the reference date”, do not reuse this algorithm as-is. In that case, you can start by checking the current candidate and only advance when it is invalid. The two contracts must be named and tested separately.

### A Single Call Does Not Mutate the Input

The line `original = 2025-06-13` shows that the input variable still holds its original date after the adjustment is applied. In calling code, you must assign or use the returned value, such as `LocalDate dueDate = original.with(nextWorking)`.

The “next working day” rule is also not idempotent. Once you already have a working day, applying it a second time advances to the following working day. Do not use this adjuster as a normalization operation that can be re-run arbitrarily if the business rule only permits shifting the date once.

### Snapshotting Clarifies the Meaning of Captured Data

`Set.copyOf(holidays)` creates an unmodifiable set for the rule. After creating the adjuster, the program adds the 17th to `source`; the result from the existing adjuster remains the 17th. This is a deliberate design choice: the adjuster's calendar is a snapshot taken at creation time, not a live view over a mutating source set.

If the application updates its holiday calendar, create a new adjuster from the appropriate calendar version or design a calendar service with an explicit update contract. Avoid letting a lambda accidentally hold a reference to a mutable set and produce different results for the same input without callers knowing.

## 6. Reusing Across Other Temporal Types

### Date-Time Types That Have a Full Date Part

The call `meeting.with(nextWorking)` returns a `LocalDateTime` for June 17 at 15:30. The lambda does not need to be rewritten for `LocalDateTime`; the time-of-day component is preserved in this example.

With `ZonedDateTime` in `Asia/Ho_Chi_Minh`, the result keeps that zone and 15:30 on the new date. This is a calendar-date adjustment, not adding a fixed number of seconds.

If the new date in a time zone has a daylight saving time transition that makes the local time nonexistent or gives it two valid offsets, re-applying the date must also follow the rules of the zoned type. Therefore, do not assume that a rule operating only on `LocalDate` will automatically handle every requirement involving time of day, offsets, or elapsed duration.

### Not Every `Temporal` Has a Full Date

`YearMonth` only has a year and a month, so a `LocalDate` cannot be extracted to pass into the lambda; the example throws `DateTimeException`. Similarly, a `LocalTime` does not provide a date. An `Instant` also has no independent local date unless placed in an appropriate time-zone context.

This shows that a return type of `TemporalAdjuster` does not guarantee the adjuster works with every temporal class. When publishing a rule, document which types and calendar semantics it supports. In this lesson, the rule is designed and tested for ISO dates and corresponding date-time values.

If an algorithm genuinely needs to inspect the time of day or adjust multiple non-date fields, consider a method with an appropriate parameter type or a dedicated `TemporalAdjuster`. Do not force all logic through `ofDateAdjuster()` and rely on workarounds to access information that was never passed to the lambda.

## 7. Writing Predictable, Reusable Rules

`ofDateAdjuster()` only wraps the function. It does not automatically make any state captured by that function immutable or thread-safe. The lambda in the example only reads an unmodifiable set and uses local variables, so concurrent calls do not overwrite each other's state.

If a rule does not depend on changing configuration, you can construct it once and reuse it via a clearly named constant. If it depends on a calendar, you can create one adjuster per calendar version or specific configuration. Avoid re-instantiating the same rule on every line of processing when the configuration data does not change.

Principles to follow:

- Return a valid `LocalDate`; do not return `null` to signal “not found”. If a problem may have no valid result within a business range, design a result or error reporting mechanism appropriate for that domain.
- Do not call `LocalDate.now()` inside the rule to replace the input date; the adjuster must adjust the reference date passed by the caller.
- Do not add database writes, notifications, or counter mutations inside the date calculation function. Keep the computation pure enough to be re-invoked and tested independently.
- Ensure the search loop always makes forward progress and define how date limits or calendar boundaries are handled. Near `LocalDate.MAX`, incrementing a day may fail rather than yield a future date.

## 8. Practice by Contract

Create a rule for “working day from the reference date, inclusive of the reference date” using the same holiday set and compare it with `nextWorkingDay()`:

| Input date | Version excluding original date | Version that may keep original date |
| --- | --- | --- |
| `2025-06-13` — Friday | `2025-06-17` | `2025-06-13` |
| `2025-06-14` — Saturday | `2025-06-17` | `2025-06-17` |
| `2025-06-16` — hypothetical holiday | `2025-06-17` | `2025-06-17` |

Keep the holiday data at the initial snapshot containing only the 16th when checking this table. This exercise tests the part the application must decide: whether the starting date counts, which weekend days are excluded, and which holiday set is used. `ofDateAdjuster()` provides the packaging; the right contract must come from the rule you write.
