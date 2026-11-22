# Calculating Business Days and Separating Holiday Policy from Calendar Arithmetic

## 1. A business day is the result of a policy

`LocalDate` represents a date on the ISO calendar, such as `2024-04-05`. It knows what day of the week that date is, knows about leap years, and knows how to move to the next day. It does not know whether a business, branch, or market operates on that date.

A **calendar day** is every consecutive day on the calendar. A **business day** is a day accepted by a business policy. A policy may include weekly days off, specific holidays, and make-up working days. Therefore, adding three calendar days and adding three business days answer two different questions.

According to the [Java API for LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), this object contains neither time of day nor time zone and does not directly represent an instant on the timeline. This article works with the day unit; it does not calculate working hours, hour-based deadlines, or shift schedules.

Hypothetical example: Friday 2024-04-05 is the request receipt date; Saturday and Sunday are off; Monday 2024-04-08 is configured as an additional holiday. Excluding the receipt date, one business day later is Tuesday 2024-04-09. Calling `plusDays(1)` simply returns Saturday 2024-04-06, because that method has no business policy parameter.

There is no default holiday calendar that fits every country or organization. All holidays and make-up working days in this article are **hypothetical data for verifying the algorithm**, not announcements of actual holiday schedules.

## 2. Separate two responsibilities before writing loops

The **policy** part answers one question:

```java
boolean isBusinessDay(LocalDate date);
```

The **calendar arithmetic** part iterates over dates, queries the policy, and decides when to stop. It does not need to know whether holidays come from a configuration file, a database, a market calendar, or branch-specific rules.

In Java, `Predicate<LocalDate>` can be used to pass that answer into the algorithm. For a small model, a calendar object with an `isBusinessDay` method passed as `calendar::isBusinessDay` is sufficient. When you need to add a calendar ID, version, or validity range, you can define a dedicated business interface; there is no need to put data loading inside the date-calculation loop.

| Component | Responsibility |
| --- | --- |
| `LocalDate` and `plusDays` | Step through the ISO calendar, including month, year, and leap-year boundaries |
| Business day policy | Classify a specific date as working or non-working |
| Addition or counting algorithm | Interval convention, direction of movement, number of accepted days |
| Calendar loader | Select the unit's calendar, validate data, and provide a stable snapshot |

Because of this separation, modifying holidays does not force changes to the algorithm. The same algorithm can serve two units with different weekend schedules.

## 3. Lock down endpoint and start-date conventions

Off-by-one errors often stem from an unclear contract, even when the loop has no syntax bugs.

### 3.1. Counting in a half-open interval

In this article, `countBusinessDays(fromInclusive, toExclusive, policy)` counts dates in the interval **[fromInclusive, toExclusive)**:

- Includes the start date if the policy classifies it as a business day.
- Excludes the end date.
- Equal endpoints return `0`.
- An end date before the start date is invalid input; do not swap the two endpoints automatically.

For example, `[2024-04-05, 2024-04-10)` consists of April 05, 06, 07, 08, and 09. If only Saturday and Sunday are off, there are three business days: 05, 08, and 09. If 08/04 is also a holiday, two remain.

`LocalDate.datesUntil(endExclusive)` fits this contract: it generates each date starting from the current date and excludes the end date. There is no need to manually add one day to the endpoint. Converting a closed interval using `endInclusive.plusDays(1)` can exceed the representable range if the end is `LocalDate.MAX`; handle this separately if the business interface chooses a closed interval.

### 3.2. Adding a number of business days

In this article, `addBusinessDays(start, amount, policy, maxCalendarSteps)` has the following contract:

- `amount > 0`: moves forward into the future and counts business days after `start`.
- `amount < 0`: moves backward into the past and counts business days before `start`.
- **Does not count the start date itself**, whether that date is working or non-working.
- `amount == 0`: returns `start` unchanged, even if it is a non-working day.
- `maxCalendarSteps` must be positive; this is the limit on calendar days allowed to be traversed, not the limit on business days.

For example, starting on Sunday 2024-04-07, adding `0` still yields 2024-04-07; adding `1` under a standard weekend schedule yields Monday 2024-04-08. If you want "add 0 but automatically shift to a business day," define a separate adjustment operation and avoid silently changing the meaning of addition.

Nor should you assume addition always has an inverse when the starting point is a non-working day. Under the contract above, Sunday 2024-04-07 plus one business day becomes Monday 2024-04-08; subtracting one business day from Monday yields Friday 2024-04-05, not back to Sunday.

## 4. Sample policy: weekends, specific holidays, and make-up days

We choose a transparent precedence order:

1. If present in the make-up working days set, it is a business day.
2. Otherwise, if present in the specific holidays set, it is a non-working day.
3. Otherwise, check the weekly days off.

Make-up working days in this example take precedence even if they overlap with a specific holiday. This is a choice of the sample policy. Another system might forbid overlapping sets or give holidays precedence; in that case, modify the policy and data validation, not the loop.

The data uses `Set` so that a duplicate holiday entry does not increase the number of times that date is excluded. `Set.copyOf` creates an unmodifiable copy via the stored reference, ensuring results do not change mid-way due to external additions or removals of holidays. `LocalDate` itself is immutable.

Do not mechanically compute "weekdays minus holidays in the list": a holiday might fall outside the interval, land on a weekend, be duplicated, or be overridden by a make-up working exception. Classifying each date with a single function avoids double-subtracting.

## 5. Complete Java 17+ program

Save the following code as `BusinessDaysDemo.java`. The program uses only the standard library and every date is constructed explicitly, independent of the machine's current date.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

public class BusinessDaysDemo {
    record BusinessCalendar(
            Set<DayOfWeek> weekend,
            Set<LocalDate> holidays,
            Set<LocalDate> workingOverrides) {

        BusinessCalendar {
            weekend = Set.copyOf(Objects.requireNonNull(weekend));
            holidays = Set.copyOf(Objects.requireNonNull(holidays));
            workingOverrides =
                    Set.copyOf(Objects.requireNonNull(workingOverrides));
        }

        boolean isBusinessDay(LocalDate date) {
            Objects.requireNonNull(date);
            if (workingOverrides.contains(date)) {
                return true;
            }
            return !holidays.contains(date)
                    && !weekend.contains(date.getDayOfWeek());
        }
    }

    static long countBusinessDays(
            LocalDate fromInclusive,
            LocalDate toExclusive,
            Predicate<LocalDate> policy) {

        Objects.requireNonNull(fromInclusive);
        Objects.requireNonNull(toExclusive);
        Objects.requireNonNull(policy);
        if (toExclusive.isBefore(fromInclusive)) {
            throw new IllegalArgumentException("Reversed interval");
        }

        return fromInclusive.datesUntil(toExclusive)
                .filter(policy)
                .count();
    }

    static LocalDate addBusinessDays(
            LocalDate start,
            int amount,
            Predicate<LocalDate> policy,
            int maxCalendarSteps) {

        Objects.requireNonNull(start);
        Objects.requireNonNull(policy);
        if (maxCalendarSteps <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }
        if (amount == 0) {
            return start;
        }

        int direction = amount > 0 ? 1 : -1;
        long remaining = Math.abs((long) amount);
        LocalDate cursor = start;

        for (int steps = 0; steps < maxCalendarSteps; steps++) {
            cursor = cursor.plusDays(direction);
            if (policy.test(cursor)) {
                remaining--;
                if (remaining == 0) {
                    return cursor;
                }
            }
        }
        throw new IllegalStateException("Calendar search limit exceeded");
    }

    static LocalDate nextBusinessDayOrSame(
            LocalDate start,
            Predicate<LocalDate> policy,
            int maxCalendarSteps) {

        Objects.requireNonNull(start);
        Objects.requireNonNull(policy);
        if (maxCalendarSteps <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }
        if (policy.test(start)) {
            return start;
        }
        return addBusinessDays(start, 1, policy, maxCalendarSteps);
    }

    public static void main(String[] args) {
        LocalDate friday = LocalDate.of(2024, 4, 5);
        LocalDate monday = LocalDate.of(2024, 4, 8);
        LocalDate wednesday = LocalDate.of(2024, 4, 10);

        BusinessCalendar normal = new BusinessCalendar(
                Set.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY),
                Set.of(),
                Set.of());

        BusinessCalendar holiday = new BusinessCalendar(
                normal.weekend(),
                Set.of(monday),
                Set.of());

        BusinessCalendar makeUp = new BusinessCalendar(
                normal.weekend(),
                Set.of(monday),
                Set.of(LocalDate.of(2024, 4, 6)));

        System.out.println("calendar +1 = " + friday.plusDays(1));
        System.out.println("normal +1 = " + addBusinessDays(
                friday, 1, normal::isBusinessDay, 30));
        System.out.println("holiday +1 = " + addBusinessDays(
                friday, 1, holiday::isBusinessDay, 30));
        System.out.println("make-up +1 = " + addBusinessDays(
                friday, 1, makeUp::isBusinessDay, 30));

        System.out.println("normal count = " + countBusinessDays(
                friday, wednesday, normal::isBusinessDay));
        System.out.println("holiday count = " + countBusinessDays(
                friday, wednesday, holiday::isBusinessDay));
        System.out.println("make-up count = " + countBusinessDays(
                friday, wednesday, makeUp::isBusinessDay));

        System.out.println("holiday -1 = " + addBusinessDays(
                LocalDate.of(2024, 4, 9), -1,
                holiday::isBusinessDay, 30));

        LocalDate sunday = LocalDate.of(2024, 4, 7);
        System.out.println("zero = " + addBusinessDays(
                sunday, 0, holiday::isBusinessDay, 30));

        TemporalAdjuster following = TemporalAdjusters.ofDateAdjuster(
                date -> nextBusinessDayOrSame(
                        date, holiday::isBusinessDay, 30));
        System.out.println("following = " + sunday.with(following));

        System.out.println("empty count = " + countBusinessDays(
                friday, friday, normal::isBusinessDay));

        try {
            addBusinessDays(friday, 1, date -> false, 10);
        } catch (IllegalStateException ex) {
            System.out.println("closed calendar = " + ex.getMessage());
        }
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 BusinessDaysDemo.java
java BusinessDaysDemo
```

Output:

```text
calendar +1 = 2024-04-06
normal +1 = 2024-04-08
holiday +1 = 2024-04-09
make-up +1 = 2024-04-06
normal count = 3
holiday count = 2
make-up count = 3
holiday -1 = 2024-04-05
zero = 2024-04-07
following = 2024-04-09
empty count = 0
closed calendar = Calendar search limit exceeded
```

### 5.1. Tracing adding one business day

With `holiday` and start date 2024-04-05:

| Iteration | Date inspected | Decision | Remaining business days |
| --- | --- | --- | --- |
| 1 | 06/04, Saturday | Weekend, skip | 1 |
| 2 | 07/04, Sunday | Weekend, skip | 1 |
| 3 | 08/04, Monday | Specific holiday, skip | 1 |
| 4 | 09/04, Tuesday | Accept | 0 |

The key point is that `remaining` decreases only when `policy.test(cursor)` returns `true`. `cursor` still advances by one day on every iteration. If the date were incremented only when encountering a business day, the algorithm would get stuck on the first non-working day.

With `makeUp`, 06/04 is accepted immediately because it is in `workingOverrides`. The addition algorithm has no "Saturday make-up" branch; it simply receives the result from the policy.

### 5.2. Stepping backward and avoiding integer overflow

When `amount` is negative, `direction` is `-1`, so `plusDays(-1)` steps backward one day at a time. From Tuesday 09/04 under `holiday`: Monday is a holiday, the weekend is off, so the first accepted date is Friday 05/04.

`Math.abs((long) amount)` converts to `long` **before** taking the absolute value. `Math.abs(Integer.MIN_VALUE)` on `int` remains negative because the absolute value exceeds the positive range of `int`. Casting prevents that bug; the traversal limit can still reject an overly large request.

`LocalDate` also has bounds. Stepping past `LocalDate.MAX` or before `LocalDate.MIN` fails rather than wrapping around. The program does not catch and turn out-of-range errors into a fake valid date.

### 5.3. What does the traversal limit protect against?

A policy could return `false` for every date. An unbounded `while (remaining > 0)` loop would never find a result and could continue all the way to the calendar boundary.

`maxCalendarSteps` gives the request an explicit resource bound. If the limit is reached, the method throws an exception rather than returning the last inspected date as if it were a successful result. Exceeding the limit does not prove the calendar never has a business day; it only indicates that enough business days could not be found within the given range.

The value `30` in the example is an illustrative configuration for very small requests, not a general formula `amount * someFactor`. For calendars with long closures, configure an appropriate limit or use a calendar interval with a validated range.

## 6. Adjusting due dates differs from adding business days

Three questions are easily confused:

| Request | Behavior when start date is already a business day |
| --- | --- |
| Next business day | Always moves forward, does not return start date |
| Next business day or same | Keeps start date |
| Add `n` business days | Follows the counting contract; this article excludes start date, `n = 0` keeps it unchanged |

`nextBusinessDayOrSame` in the program serves the second question. When the start date is already valid, it returns immediately; otherwise, it uses adding one business day to search forward.

[TemporalAdjusters.ofDateAdjuster](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#ofDateAdjuster(java.util.function.UnaryOperator)) wraps a `LocalDate` adjustment function into a `TemporalAdjuster` so it can be called via `date.with(adjuster)`. It does not add a holiday database; the business logic is still decided by the passed-in function.

`TemporalAdjusters.next(DayOfWeek.MONDAY)` finds the next Monday, but that Monday might be a holiday under the policy. Finding a specific day of the week and finding a business day are two adjustments with distinct meanings.

In financial domains, you sometimes need a "modified following" rule: "move to the next business day, unless that crosses into a new month, in which case move backward." That is a different contract and must be specified and tested separately; do not give it a generic name like `fixDate` and silently apply it to every payment due date.

## 7. Calendar data must be meaningful and scoped

### 7.1. Holidays are data, not algorithm constants

A real-world calendar typically needs to know the calendar/unit ID, applicable region, covered year or date range, data source, and version. Two units located in the same country can still have different operating calendars.

The hypothetical calendar in the program is treated as complete for the dates under consideration. `Set.of()` means "no additional holidays in the sample configuration," not proof that a real year has no public holidays.

If only 2024 data is loaded and a calculation crosses into 2025, an empty holiday set for 2025 is **missing information**, not necessarily a working day. You can wrap the policy with a validity-range check and reject any date outside the range. For counting, validate the entire requested interval before traversing; for addition, validate each date or constrain the search within the known range. Missing data should be reported explicitly rather than guessing holidays.

Observed holidays, compensatory days off, or shifted holidays belong to the supplied calendar data. Do not hardcode "if a holiday falls on Sunday, then Monday is off" unless a policy explicitly requires it.

### 7.2. Maintain a consistent snapshot

Load and validate the calendar first, then compute against an immutable snapshot. If every call to `isBusinessDay` queried a remote API, addition could be slow, fail mid-way due to network errors, or use two different calendar versions within a single calculation.

To explain a result later, you can record the start date, amount added, calendar ID, calendar version, and endpoint convention. If a cache uses only the date and amount as its key, two branches with different calendars could mistakenly receive the same result. The key must reflect both the policy and its corresponding version.

In the example, `BusinessCalendar` uses immutable sets and holds no mutable state during calculation. If you pass another `Predicate` that has mutable state or random results, the algorithm cannot guarantee consistency on its own; the policy contract should require that the same date against the same calendar snapshot always returns the same answer.

### 7.3. Converting an instant to a date requires choosing a business time zone

Date addition itself does not require a time zone. However, if the input is an `Instant`, you must choose the unit's time zone before obtaining a `LocalDate`; near midnight, the same instant can belong to two different dates in two different time zones.

A daily business calendar is also insufficient for deciding deadlines with a daily cutoff time. For example, a rule that requests received after 17:00 are counted from the next day is a separate business step requiring `LocalTime` or an appropriate date-time type.

Do not convert one business day into `24` hours to add to an `Instant`: hours on the timeline and business days are two different quantities. This article only counts dates accepted by the policy.

## 8. Complexity and when to optimize

`countBusinessDays` traverses `D` days in the interval, resulting in `D` policy calls. `addBusinessDays` traverses `K` calendar days until enough business days are found, up to the configured limit. If classifying a date has average constant cost, the time complexities are `O(D)` and `O(K)` respectively; hash-set membership checks typically fit this requirement.

Day-by-day traversal is easy to explain and verify, and is usually sufficient for deadlines of a few days or a few months. It does not allocate the entire list of dates in memory; the `datesUntil` stream is consumed to count. Holiday data still occupies memory proportional to the configured set size.

The formula "each week has five business days" only applies when the calendar satisfies that assumption. Additional holidays and make-up days break simple step jumps. If you genuinely need high-throughput processing over a fixed range, you can precompute working/non-working flags and prefix sums by date; in return, you must manage the data domain and rebuild the index whenever the calendar version changes.

Do not optimize by scattering holiday rules across multiple algorithms. Whether using a loop or an index, keep a single unified policy definition so counting and addition results never contradict each other.

## 9. Common mistakes and how to recognize them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `plusDays(n)` to add business days | Includes weekends and holidays | Traverse dates and query the policy |
| Hardcoding Saturday and Sunday off in multiple functions | Hard to switch calendars for other units | Pass a shared policy |
| Subtracting all holidays from weekdays | Double-subtracts weekend holidays and subtracts out-of-range holidays | Classify each date or filter the set per the contract |
| Counting both endpoints while naming the parameter `endExclusive` | Off by one day | Document the interval clearly and use it consistently |
| Automatically shifting a non-working day when adding `0` | Behavior differs from the contract without callers knowing | Separate the date-adjustment operation |
| Ignoring make-up working days | Results are later than the policy specifies | Define exception precedence order |
| Assuming an empty holiday list is always a valid calendar | Turns missing data into business days | Check the validity range and calendar load status |
| Not bounding the search | Wastes resources on calendars with no business days | Limit traversal steps or validity range |
| Ignoring the return value of `plusDays` | Cursor never changes because `LocalDate` is immutable | Reassign `cursor = cursor.plusDays(...)` |
| Dividing elapsed hours by `24` | Confuses duration with business days | Compute using `LocalDate` and the policy |

## 10. Self-verification and practice

Test cases should vary the meaning of the input, not just the number of days:

1. **Equal endpoints:** number of business days is `0`, whether that date is working or non-working.
2. **Weekend:** from 2024-04-05, the normal calendar plus one day yields 2024-04-08.
3. **Monday holiday:** same input, the `holiday` calendar yields 2024-04-09.
4. **Saturday make-up day:** same input, the `makeUp` calendar yields 2024-04-06.
5. **Holiday falling on a weekend:** add 2024-04-06 to the holiday set of the normal calendar; the result is not subtracted a second time.
6. **Negative and zero amounts:** subtracting one day from 2024-04-09 under `holiday` yields 2024-04-05; adding `0` from Sunday keeps Sunday unchanged.
7. **Month change and leap year:** using a weekend-only calendar, from 2024-02-28 adding one business day yields 2024-02-29, and from 2024-02-29 adding one yields 2024-03-01.
8. **Year change:** with a weekend-only calendar and no additional holidays, from 2024-12-31 adding one business day yields 2025-01-01. This only tests the algorithm on a hypothetical calendar and does not assert that 01/01 is an actual business day.
9. **Policy rejecting every date:** the request must terminate with a limit error, neither hanging nor returning an invalid date.
10. **Reversed interval or out-of-range calendar:** invalid input must fail explicitly.

Exercises:

- Create a calendar with Friday and Saturday off while keeping all algorithms unchanged. Verify that Sunday can be accepted.
- Write `previousBusinessDayOrSame` with a contract analogous to the forward search; test both a non-working and a working start date.
- Add a wrapper restricting the calendar to `[validFrom, validToExclusive)`, then request a calculation beyond the loaded year. The system should report missing calendar data rather than returning a result based on an incomplete holiday set.
- Explain why two calculations using the same start date and amount can still produce different results when the calendar ID or calendar version differs.

The target competency is to clearly articulate "which dates are accepted" and "how dates are traversed and counted." When those two parts have separate contracts, changing holidays becomes a testable policy change while calendar arithmetic remains consistent.
