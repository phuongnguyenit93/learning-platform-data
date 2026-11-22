# Calculating the Next Working Day Based on a Holiday Policy

## 1. Practice Problem

A request-processing department needs to answer:

> After the intake date, what is the nearest working day according to the department's operating calendar?

You cannot simply call `plusDays(1)` and assume you already have the answer. The next day could be a weekly day off, a special closure day, or conversely, an extra open day.

In this practice exercise, we build a solution with:

- Clear input and start-date conventions.
- An object describing the holiday policy.
- An algorithm to find the nearest day.
- A finite calendar data range.
- A runnable Java 17+ program with verifiable results.

**All special closure and extra open dates in this exercise are hypothetical data.** They do not represent the actual holiday calendar of any country or business.

The goal is not to memorize a list of holidays, but to turn the policy into data and ensure the algorithm respects that policy.

## 2. Write the Contract Before Writing the Loop

The name `nextWorkingDayAfter` is chosen with a strict meaning:

1. Do not consider the input date itself.
2. Start checking from the next calendar day.
3. Return the first working day found.
4. If no result exists within the provided calendar range, throw an error.
5. Do not fabricate holidays, automatically load another year's calendar, or guess the status outside the range.

For example, if Friday is a working day:

| Requirement | Can the result be the input Friday? |
| --- | --- |
| "The working day after Friday" | No |
| "A working day from Friday onward, including that day" | Yes |

We provide a separate function `workingDayOnOrAfter` for the second contract. Splitting the names ensures callers do not have to guess what an `includeStart` flag passed at each call site means.

`LocalDate` is suitable because the problem operates at day granularity. According to [LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), this type contains no time of day or time zone, and calculations return new objects. If the application's input is an `Instant`, you need to determine the intake date in the business time zone before calling this algorithm.

## 3. Preparing the Calendar Data

The sample policy has five components:

| Component | Meaning |
| --- | --- |
| `validFromInclusive` | The first date with calendar data |
| `validToExclusive` | The end date excluded from the calendar range |
| `weeklyDaysOff` | Days of the week that recur as weekly days off |
| `closedDates` | Additional closure dates |
| `extraOpenDates` | Special open dates |

The calendar range is the half-open interval `[validFromInclusive, validToExclusive)`. For example, `[2024-01-01, 2025-01-01)` has data for every day of 2024, excluding 01/01/2025.

### 3.1. Rules for Classifying a Date

The policy in this exercise chooses:

1. The date must be within the known range.
2. If it belongs to `extraOpenDates`, it is a working day, even if it falls on a weekly day off.
3. If it belongs to `closedDates`, it is a day off.
4. If there is no override, check `weeklyDaysOff`.

A date must not be in both `closedDates` and `extraOpenDates` at the same time. The constructor will reject conflicting data rather than silently picking a precedence between the two overrides.

This is a sample contract. Another business domain might allow conflicts and pick one side to take precedence, but in that case the different policy must be documented and verified. The day-finding loop should not contain those decisions itself.

### 3.2. Using DayOfWeek Instead of Hard-to-Remember Numbers

[DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html) represents days of the week as an enum. The set:

```java
Set.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY)
```

expresses intent more clearly than a pair of numbers. If you need a Friday–Saturday weekend schedule, you only change the configuration set without modifying the algorithm.

Weekly days off must not be inferred from the UI language. A user reading Vietnamese may still work with a unit whose weekly days off are not Saturday and Sunday.

### 3.3. Fixing a Calendar Snapshot During a Calculation

[Set.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) creates a set that cannot be modified through the held reference. The `LocalDate` and `DayOfWeek` elements in this exercise are also immutable values.

As a result, if external code modifies the input set after creating the calendar, the policy's snapshot is not altered along with it. The algorithm will not encounter a case where the 16th is treated as a day off in one iteration and suddenly turns into a working day in the same calculation run.

The constructor also checks that override dates fall within the calendar range. An override from another year accidentally placed into 2024 data must be detected early.

## 4. Algorithm for Finding the Nearest Day

The algorithm can be expressed in the following steps:

1. Check that the start date is within the calendar range.
2. Set the candidate to the start date plus one day.
3. While the candidate has not reached the exclusive end bound:
   - Ask the policy whether the candidate is a working day.
   - If yes, return the candidate immediately.
   - If no, advance to the next calendar day.
4. If the range is exhausted without finding one, report that there is no result within the known calendar.

The reason the result is the **nearest**: dates are inspected in ascending order day by day, and the first accepted date is returned immediately. No date between the start date and the result is skipped.

If you only advance the candidate when encountering a working day, the loop will get stuck on a day off. The pointer must advance after every unsuccessful check.

Do not use a fixed jump like "if Friday, add three days" because Monday might be closed, or Saturday might be specially opened. The policy has the complete answer for every day; the algorithm should query the policy uniformly.

## 5. Complete Java 17+ Program

Save as `NextWorkingDayPractice.java`:

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NextWorkingDayPractice {
    record WorkCalendar(
            LocalDate validFromInclusive,
            LocalDate validToExclusive,
            Set<DayOfWeek> weeklyDaysOff,
            Set<LocalDate> closedDates,
            Set<LocalDate> extraOpenDates) {

        WorkCalendar {
            Objects.requireNonNull(validFromInclusive);
            Objects.requireNonNull(validToExclusive);
            if (!validFromInclusive.isBefore(validToExclusive)) {
                throw new IllegalArgumentException("Empty calendar coverage");
            }
            weeklyDaysOff = Set.copyOf(weeklyDaysOff);
            closedDates = Set.copyOf(closedDates);
            extraOpenDates = Set.copyOf(extraOpenDates);
            if (!Collections.disjoint(closedDates, extraOpenDates)) {
                throw new IllegalArgumentException("Conflicting date overrides");
            }
            Set<LocalDate> exceptions = new HashSet<>(closedDates);
            exceptions.addAll(extraOpenDates);
            for (LocalDate date : exceptions) {
                if (date.isBefore(validFromInclusive)
                        || !date.isBefore(validToExclusive)) {
                    throw new IllegalArgumentException(
                            "Override outside calendar coverage");
                }
            }
        }

        boolean covers(LocalDate date) {
            Objects.requireNonNull(date);
            return !date.isBefore(validFromInclusive)
                    && date.isBefore(validToExclusive);
        }

        boolean isWorkingDate(LocalDate date) {
            if (!covers(date)) {
                throw new DateTimeException("Date outside calendar coverage");
            }
            if (extraOpenDates.contains(date)) {
                return true;
            }
            if (closedDates.contains(date)) {
                return false;
            }
            return !weeklyDaysOff.contains(date.getDayOfWeek());
        }
    }

    static LocalDate nextWorkingDayAfter(
            LocalDate startExclusive, WorkCalendar calendar) {
        Objects.requireNonNull(startExclusive);
        Objects.requireNonNull(calendar);
        if (!calendar.covers(startExclusive)) {
            throw new DateTimeException("Start outside calendar coverage");
        }

        for (LocalDate candidate = startExclusive.plusDays(1);
                candidate.isBefore(calendar.validToExclusive());
                candidate = candidate.plusDays(1)) {
            if (calendar.isWorkingDate(candidate)) {
                return candidate;
            }
        }
        throw new DateTimeException("No working day in covered range");
    }

    static LocalDate workingDayOnOrAfter(
            LocalDate startInclusive, WorkCalendar calendar) {
        Objects.requireNonNull(calendar);
        if (calendar.isWorkingDate(startInclusive)) {
            return startInclusive;
        }
        return nextWorkingDayAfter(startInclusive, calendar);
    }

    public static void main(String[] args) {
        LocalDate from = LocalDate.of(2024, 1, 1);
        LocalDate until = LocalDate.of(2025, 1, 1);
        Set<DayOfWeek> weekend =
                Set.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY);

        WorkCalendar normal = new WorkCalendar(
                from, until, weekend, Set.of(), Set.of());
        WorkCalendar closure = new WorkCalendar(
                from, until, weekend,
                Set.of(LocalDate.of(2024, 9, 16),
                       LocalDate.of(2024, 9, 17)),
                Set.of());
        WorkCalendar extraOpen = new WorkCalendar(
                from, until, weekend, closure.closedDates(),
                Set.of(LocalDate.of(2024, 9, 14)));

        LocalDate friday = LocalDate.of(2024, 9, 13);
        System.out.println("normal after Friday = "
                + nextWorkingDayAfter(friday, normal));
        System.out.println("closure after Friday = "
                + nextWorkingDayAfter(friday, closure));
        System.out.println("extra-open after Friday = "
                + nextWorkingDayAfter(friday, extraOpen));
        System.out.println("on-or-after Friday = "
                + workingDayOnOrAfter(friday, closure));
        System.out.println("closure after Sunday = "
                + nextWorkingDayAfter(LocalDate.of(2024, 9, 15), closure));
        System.out.println("leap day = " + nextWorkingDayAfter(
                LocalDate.of(2024, 2, 28), normal));

        WorkCalendar fridaySaturdayOff = new WorkCalendar(
                from, until,
                Set.of(DayOfWeek.FRIDAY, DayOfWeek.SATURDAY),
                Set.of(), Set.of());
        System.out.println("different weekend = "
                + nextWorkingDayAfter(friday, fridaySaturdayOff));

        WorkCalendar closedEveryDay = new WorkCalendar(
                from, until, EnumSet.allOf(DayOfWeek.class),
                Set.of(), Set.of());
        try {
            nextWorkingDayAfter(LocalDate.of(2024, 12, 29), closedEveryDay);
        } catch (DateTimeException ex) {
            System.out.println("no result = " + ex.getMessage());
        }

        try {
            nextWorkingDayAfter(LocalDate.of(2024, 12, 31), normal);
        } catch (DateTimeException ex) {
            System.out.println("coverage limit = " + ex.getMessage());
        }

        try {
            new WorkCalendar(from, until, weekend,
                    Set.of(friday), Set.of(friday));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid policy = " + ex.getMessage());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 NextWorkingDayPractice.java
java NextWorkingDayPractice
```

Stdout:

```text
normal after Friday = 2024-09-16
closure after Friday = 2024-09-18
extra-open after Friday = 2024-09-14
on-or-after Friday = 2024-09-13
closure after Sunday = 2024-09-18
leap day = 2024-02-29
different weekend = 2024-09-15
no result = No working day in covered range
coverage limit = No working day in covered range
invalid policy = Conflicting date overrides
```

The program uses only the standard library. It requires no database, network, or the machine's current date.

## 6. Reading the Results by Scenario

### 6.1. Regular Weekly Days Off

The start date is Friday 13/09/2024. The `normal` calendar is off on Saturday and Sunday, with no overrides:

| Candidate | Conclusion |
| --- | --- |
| 14/09, Saturday | Weekly day off |
| 15/09, Sunday | Weekly day off |
| 16/09, Monday | First working day |

The result is 16/09.

### 6.2. Two Closure Dates After the Weekend

The `closure` calendar adds closure dates 16/09 and 17/09. Both weekend days are still off; the two following days are also off; 18/09 is the first accepted day.

The result changes to 18/09 without modifying `nextWorkingDayAfter`.

This is proof that the algorithm does not depend on a specific holiday list. It only uses `WorkCalendar`'s date-classification interface.

### 6.3. An Extra Open Date

The `extraOpen` calendar allows working on Saturday 14/09. Because it is the first candidate after Friday and the policy allows working, the result is 14/09.

There is no need to add a "if Saturday make-up workday" branch to the loop. The override lives inside the policy object.

### 6.4. Counting From the Input Date vs. After the Input Date

`workingDayOnOrAfter` receives Friday 13/09, sees that it is already a working day, and returns 13/09 itself. `nextWorkingDayAfter` with the same date always advances at least one day before checking.

Both differing results are correct according to their respective contracts. When a caller chooses the wrong function, you should not fix it by arbitrarily offsetting by one day; you need to determine whether the requirement genuinely wants to exclude or include the start date.

### 6.5. A Calendar With Different Weekly Days Off

`fridaySaturdayOff` is off on Friday and Saturday. After Friday 13/09, Saturday is off, but Sunday 15/09 is accepted.

Sunday is not an absolute day off in `LocalDate`. Working/non-working status comes from the calendar's policy.

### 6.6. Leap Year

After 28/02/2024, the normal calendar accepts 29/02. The algorithm does not need to calculate the number of days in February itself; `LocalDate.plusDays` handles calendar boundaries.

Similarly, month and year transitions belong to Java's calendar arithmetic, while whether the new date is a working day belongs to the policy.

## 7. Calendar Coverage Prevents Guessing Missing Data

31/12/2024 is within the sample calendar, but the day after it is outside `validToExclusive`. The function must not look at `closedDates`, see that 01/01/2025 is absent, and conclude that 01/01 is a working day.

Having no holiday entries for 2025 may simply mean **data for that year is not yet available**.

In the program:

```text
coverage limit = No working day in covered range
```

This message only says no working day was found within the provided range. It does not assert that there will never be a working day after that.

If you want to calculate into the new year, the data-preparation layer must provide a calendar snapshot with an appropriate coverage range. Do not let the loop call a network service on every day, because loading the calendar and computing the date have different responsibilities.

Similarly, a start input outside the range is rejected immediately. This exercise chooses this contract to avoid a request where it is unclear whether the start date is known to the calendar. You can design a different API for starting just before the range, but it must be defined separately.

## 8. Why Does an Every-Day-Closed Calendar Still Terminate?

`closedEveryDay` configures all seven days of the week as days off. With no extra open dates, no candidate is accepted.

The loop still stops at `validToExclusive` and throws an error. It is not a `while (true)` loop waiting for a working day that is not guaranteed to exist.

In the example, a one-year range is finite and small. For a system that allows very large ranges, you should add a reasonable limit on the number of days that can be searched or the year range the application accepts. An exceeded resource limit must also be reported clearly, rather than returning the last candidate as if it were a working day.

Coverage range answers "how far does this data know"; a search limit answers "how much work is this request allowed to spend". Both concepts can coexist in a larger implementation.

## 9. Verifying Important Properties

Checking a few sample dates is necessary, but the problem also has properties to verify:

1. The result must be after the start date for `nextWorkingDayAfter`.
2. The result must be accepted by the policy.
3. Every date between the start date and the result must be a day off.
4. The result must be within the known range.
5. The same input and the same policy snapshot must produce the same result.

The following method snippet illustrates verifying the nearest-day property. It can be added to the example class to check a result; it is not a standalone program:

```java
static void verifyNearest(
        LocalDate startExclusive,
        LocalDate result,
        WorkCalendar calendar) {

    if (!result.isAfter(startExclusive)) {
        throw new AssertionError("Result must be after start");
    }
    if (!calendar.isWorkingDate(result)) {
        throw new AssertionError("Result must be a working date");
    }
    for (LocalDate date = startExclusive.plusDays(1);
            date.isBefore(result);
            date = date.plusDays(1)) {
        if (calendar.isWorkingDate(date)) {
            throw new AssertionError("An earlier working date was skipped");
        }
    }
}
```

This checks the actual property of the problem. If you only check `result.isAfter(start)`, a buggy function returning a working day two weeks later would still pass.

Do not use `assert` while forgetting that the assert mechanism can be disabled in normal execution. The verification example above throws `AssertionError` explicitly when a property is violated.

## 10. Invalid Data Cases That Must Be Detected

| Invalid data | Solution behavior |
| --- | --- |
| Range start date on or after end date | Reject calendar creation |
| A date is both closed and extra open | Reject conflicting policy |
| Override date outside declared range | Reject calendar data |
| Set contains a `null` element | `Set.copyOf` rejects |
| Start date outside range | Throw error, do not search further |
| Range exhausted with no result | Report no working day in range |

This validation does not prove the calendar data is business-correct. Someone accidentally entering a holiday on the 17th instead of the 16th can still create a structurally valid configuration. Calendar sources and data-review workflows need to be managed in the policy-preparation layer.

This practice exercise deliberately uses hypothetical data to verify the mechanism. Do not take a set of dates from the example and put them into a real system as if they were a confirmed holiday calendar.

## 11. Placing the Algorithm in an Application

A sensible separation of responsibilities:

| Component | Responsibility |
| --- | --- |
| Request intake layer | Determine the start date and which unit's calendar applies |
| Calendar loader | Read holidays/open dates and coverage range |
| `WorkCalendar` | Validate data, classify dates |
| Day-finding function | Traverse within bounds and return the nearest date |
| Display or persistence layer | Format/save as required |

If the input is an instant in time, the intake layer must choose the business time zone before extracting `LocalDate`. Near midnight, the same `Instant` can be two different dates in two time zones.

If a request received after a cutoff time is considered received the next day, the cutoff rule is a separate step before the search or part of an explicitly stated business workflow. Do not sneak time-of-day into `LocalDate` via a guess.

If you need an execution timestamp at the opening hour of the found date, the `LocalDate` result is only part of it. You need to combine the time, the zone, and handle cases where local date-time does not exist or is not unique if the zone has an offset change.

## 12. Complexity and Limits of Traversal

If `K` candidates must be checked before finding a result, the algorithm calls the policy `K` times. With sets having constant average-case lookup cost, the corresponding time is `O(K)`.

The loop's auxiliary memory is constant: it only holds the candidate date. The policy's memory depends on the sizes of the override sets.

For requests finding the next day in a one-year calendar, traversal is easy to understand and verify. If a system needs to compute very frequently over the same large dataset, you can precompute a working-day index. The index must be tied to the exact calendar version and range; changing holidays without rebuilding derived data will yield stale results.

Do not optimize by duplicating weekly day-off rules in multiple places. Whether using a loop or an index, you need a single consistent policy definition so results do not contradict each other.

## 13. Extension Exercises

### 13.1. Expand the Verification Test Suite

Create cases for:

- Input date is a working Thursday; the next day is Friday.
- Input date is a day off, but the next day is open.
- Multiple consecutive closure dates crossing a month boundary.
- An extra open date falling right on a weekend.
- Inputs at the first date of the range and the last date of the range.
- A calendar off every day of the week except for one extra open date in the range.
- The same date in both override sets, which must be rejected.

For each case, explain the answer by listing the rejected candidates and the reasons. Do not just state a single result date without the policy used.

### 13.2. Extend to n Working Days

Design a function to add `n` working days with a clear contract for:

- `n = 0`.
- Whether the start date counts.
- Whether negative numbers are allowed.
- What to do if the calendar range is insufficient.

Do not assume calling the next-day function `n` times is enough for every contract. It can be one implementation approach, but you must consider cost, coverage range, and the meaning of boundary values.

### 13.3. Provide an Explanation of the Result

Instead of returning only `LocalDate`, you can create a result type containing the found date and the reasons why candidates were skipped. This is useful for a learning tool or when a processing deadline needs to be explained.

Do not let the explanation become a second source of truth for the policy. Reasons and decisions must be computed consistently from the same data; do not write a separate holiday list just for display.

### 13.4. Distinguish Missing Calendar Data From No Open Days in the Calendar

In the example, running out of range is reported with an exception and a clear message. A larger API might need distinct result types for missing data, a calendar with no open days in the allowed interval, or invalid input.

If you choose such a result type, preserve that distinction when displaying errors. Do not turn every case into `null`, leaving callers unable to tell whether to load more data, fix the configuration, or report that no result exists.

## 14. Practice Completion Criteria

A solution that meets the exercise requirements does not just produce 16/09 in the normal case. It must demonstrate:

- Understanding and upholding the exclusive/inclusive start-date contract.
- Separating the policy from calendar traversal.
- Changing the day-off set can change the result without modifying the algorithm.
- Handling extra open dates and conflicting data.
- Not guessing dates outside the data range.
- Stopping when no date is found and reporting a meaningful status.
- Ensuring the result is genuinely the nearest working day.
- Verifying weekends, overrides, leap years, and range limits.

Through this exercise, calendar arithmetic and business policy are connected by a simple question: "is this date a working day?". The contract and data determine the answer; the algorithm only needs to traverse in the right order and stop under the right condition.
