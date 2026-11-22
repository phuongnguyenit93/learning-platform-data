# Checking Validity Intervals Using the Half-Open Convention

## 1. The half-open interval answers boundary questions

Suppose a policy is valid from 09:00 to 10:00. Is it already valid at exactly 09:00? Is it still valid at exactly 10:00? If the next interval starts at 10:00, which interval does that instant belong to?

The half-open convention answers clearly:

```text
[fromInclusive, untilExclusive)

Includes the start instant.
Excludes the end instant.
```

For the interval `[09:00, 10:00)`:

| Check instant | Valid? |
| --- | --- |
| Before 09:00 | No |
| Exactly 09:00 | Yes |
| After 09:00 and before 10:00 | Yes |
| Exactly 10:00 | No |
| After 10:00 | No |

This convention is especially useful for contiguous validity intervals, booking schedules, day-partitioned data, and time-versioned policies.

This exercise uses finite, non-empty intervals with the condition `fromInclusive < untilExclusive`. Both bounds are `Instant`, because validity is checked at a specific point on the timeline.

## 2. Condition for containing an instant

An instant `t` belongs to the interval when:

```text
fromInclusive <= t AND t < untilExclusive
```

In Java:

```java
// Illustrates when fromInclusive, untilExclusive, and t are all Instant.
boolean active =
        !t.isBefore(fromInclusive) && t.isBefore(untilExclusive);
```

The first part uses `!isBefore` to include the case equal to the start bound. The second part uses `isBefore` to exclude the case equal to the end bound.

Two common mistakes:

- Using `t.isAfter(from)`: loses validity at the exact start bound.
- Using `!t.isAfter(until)`: includes the end bound in the interval.

Do not compare formatted strings instead of these comparisons. `Instant` compares points in time, independent of how local date-time is printed. The model and comparisons are described at [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).

## 3. Why do two adjacent intervals not double-count?

Consider:

```text
Interval A: [09:00, 10:00)
Interval B: [10:00, 11:00)
```

At 10:00:

- A does not contain that instant.
- B contains that instant.

Thus, the same boundary is used as the end of the previous interval and the start of the next interval without being counted twice. There is also no need to create a gap by adding or subtracting one millisecond.

If both intervals included the end bound, 10:00 could belong to both A and B. If both excluded the start bound, the start instant could be missed. Half-open provides a consistent chaining convention.

Intervals can still overlap if data is created like `[09:00, 10:30)` and `[10:00, 11:00)`. The bound convention alone does not guarantee all records are non-overlapping; that requires a separate data rule if the business logic demands it.

## 4. Validate the interval before checking validity

The pattern in this exercise requires:

1. Both bounds are non-`null`.
2. The start bound must be before the end bound.
3. The data type and semantics of both bounds must be consistent.

Mathematically, `[a, a)` is an empty interval. However, the `Window` object in this exercise represents a validity interval that must have positive length, so it rejects both equal bounds and reversed order.

If an application's model allows empty intervals, that behavior must be implemented and tested consistently. In particular, the overlap formula must not accidentally treat an empty interval as "overlapping" another interval.

This exercise also does not use `null` to represent "no expiration date". An unbounded interval is a different design and needs to be stated explicitly. Do not use an arbitrary huge date as the end bound and assume every store and time-zone conversion can represent it.

## 5. Checking the current time with Clock

A function asking "is it currently active?" needs a source for the current instant. Instead of calling `Instant.now()` in scattered places, it can accept a `Clock`:

```java
// Illustrates inside a method with window and clock.
Instant reference = clock.instant();
boolean active = window.contains(reference);
```

Read one reference instant and reuse it for decisions within the same processing pass. If the clock is read multiple times near the end bound, the results can fall on opposite sides of the boundary.

In tests, use `Clock.fixed` at the exact start and exact end of the interval. Do not use `Thread.sleep` hoping the program runs at the exact moment you want to check. `Clock` is designed to substitute the time source in tests; see [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).

Note: `contains` returning `false` may mean **not started yet** or **already expired**. Do not equate "not valid" with "expired". If the UI needs to distinguish them, check status across three regions:

```text
t < from             → not started yet
from <= t < until    → valid
t >= until           → expired
```

## 6. When do two intervals overlap?

For two non-empty intervals:

```text
A = [aStart, aEnd)
B = [bStart, bEnd)
```

They overlap when:

```text
aStart < bEnd AND bStart < aEnd
```

Both comparisons are strict. Because of that, A ending at the exact moment B starts is not considered overlapping.

When there is an intersection:

- The start bound of the intersection is the later start bound.
- The end bound of the intersection is the earlier end bound.

In the program, `intersection` returns `Optional.empty()` when they do not intersect. If they only touch at a single point, the intersection is also empty because the shared point does not belong to both half-open intervals.

Do not create a `Window` with two equal bounds to represent the non-intersecting case in this model, because the constructor's contract rejects empty intervals.

## 7. Converting user-selected date ranges to instant intervals

Users may enter "from 1/5 through 31/5". These are two dates **inclusive of the last day**, unlike an exclusive instant bound.

If the business chooses the time zone `Asia/Ho_Chi_Minh`, convert as follows:

```text
Start bound: start of day 2024-05-01 in the business zone
End bound:   start of day 2024-06-01 in the same zone, exclusive
```

Corresponding instants in the example:

```text
[2024-04-30T17:00Z, 2024-05-31T17:00Z)
```

The UTC date at a bound may differ from the date the user entered. That does not mean the conversion is wrong; you need to view the bound in the right business zone.

How to compute it:

```java
// Illustrates inside a method.
Instant from = firstDate.atStartOfDay(zone).toInstant();
Instant until = lastDateInclusive.plusDays(1)
        .atStartOfDay(zone).toInstant();
```

Do not take `23:59:59` of the last day. That drops the remaining fractional second. Also do not subtract one nanosecond from the start of the next day to create a "final instant", because the storage precision may differ from Java's.

`atStartOfDay(zone)` returns the earliest valid time according to the zone rules. The start of the next day must be computed from the next calendar date, not assumed to be the start bound plus 24 hours. These rules are described at [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

On 2024-03-31 in Paris, the program shows the interval from the start of that day to the start of the next day is 23 hours long. Other offset changes can also occur; the half-open convention stays the same, and only the bound instants change according to the zone calendar.

If the last date is already at the representation limit and cannot have one day added, the conversion must be handled according to the domain data contract. Do not ignore the error and silently use an incorrect bound.

## 8. Standalone Java 17+ program

Save the following code as `HalfOpenValidity.java`. The program requires no external libraries.

`Window` represents a non-empty validity interval. `forInclusiveDates` converts an inclusive date UI range into a half-open instant interval in an explicitly passed zone.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.Optional;

public class HalfOpenValidity {
    public record Window(Instant fromInclusive, Instant untilExclusive) {
        public Window {
            Objects.requireNonNull(fromInclusive, "fromInclusive");
            Objects.requireNonNull(untilExclusive, "untilExclusive");
            if (!fromInclusive.isBefore(untilExclusive)) {
                throw new IllegalArgumentException("from must be before until");
            }
        }

        public boolean contains(Instant value) {
            Objects.requireNonNull(value, "value");
            return !value.isBefore(fromInclusive) && value.isBefore(untilExclusive);
        }

        public boolean isActive(Clock clock) {
            return contains(Objects.requireNonNull(clock, "clock").instant());
        }

        public boolean overlaps(Window other) {
            Objects.requireNonNull(other, "other");
            return fromInclusive.isBefore(other.untilExclusive)
                    && other.fromInclusive.isBefore(untilExclusive);
        }

        public Optional<Window> intersection(Window other) {
            if (!overlaps(other)) {
                return Optional.empty();
            }
            Instant from = fromInclusive.isAfter(other.fromInclusive)
                    ? fromInclusive : other.fromInclusive;
            Instant until = untilExclusive.isBefore(other.untilExclusive)
                    ? untilExclusive : other.untilExclusive;
            return Optional.of(new Window(from, until));
        }
    }

    public static Window forInclusiveDates(LocalDate first, LocalDate last,
                                           ZoneId zone) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(last, "last");
        Objects.requireNonNull(zone, "zone");
        if (first.isAfter(last)) {
            throw new IllegalArgumentException("first date must not be after last");
        }
        return new Window(first.atStartOfDay(zone).toInstant(),
                last.plusDays(1).atStartOfDay(zone).toInstant());
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
        Instant a = Instant.parse("2024-05-01T09:00:00Z");
        Instant b = Instant.parse("2024-05-01T10:00:00Z");
        Instant c = Instant.parse("2024-05-01T11:00:00Z");
        Window first = new Window(a, b);
        Window adjacent = new Window(b, c);
        Window crossing = new Window(a.plusSeconds(1800), c);

        eq(first.contains(a.minusNanos(1)), false);
        eq(first.contains(a), true);
        eq(first.contains(a.plusNanos(1)), true);
        eq(first.contains(b.minusNanos(1)), true);
        eq(first.contains(b), false);
        eq(first.contains(b.plusNanos(1)), false);
        eq(adjacent.contains(b), true);
        eq(first.overlaps(adjacent), false);
        eq(adjacent.overlaps(first), false);
        eq(first.overlaps(crossing), true);
        eq(crossing.overlaps(first), true);
        eq(first.intersection(adjacent), Optional.empty());
        eq(first.intersection(crossing),
                Optional.of(new Window(a.plusSeconds(1800), b)));
        eq(first.overlaps(first), true);
        eq(first.isActive(Clock.fixed(a, ZoneOffset.UTC)), true);
        eq(first.isActive(Clock.fixed(b, ZoneOffset.UTC)), false);
        rejects(() -> new Window(a, a));
        rejects(() -> new Window(b, a));

        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        Window may = forInclusiveDates(LocalDate.of(2024, 5, 1),
                LocalDate.of(2024, 5, 31), businessZone);
        eq(may.fromInclusive(), Instant.parse("2024-04-30T17:00:00Z"));
        eq(may.untilExclusive(), Instant.parse("2024-05-31T17:00:00Z"));
        eq(may.contains(may.untilExclusive().minusNanos(1)), true);
        eq(may.contains(may.untilExclusive()), false);
        rejects(() -> forInclusiveDates(LocalDate.of(2024, 6, 1),
                LocalDate.of(2024, 5, 31), businessZone));

        Window spring = forInclusiveDates(LocalDate.of(2024, 3, 31),
                LocalDate.of(2024, 3, 31), ZoneId.of("Europe/Paris"));
        eq(Duration.between(spring.fromInclusive(),
                spring.untilExclusive()).toHours(), 23L);

        System.out.println("activeAtStart=" + first.contains(a));
        System.out.println("activeAtEnd=" + first.contains(b));
        System.out.println("adjacentActiveAtBoundary=" + adjacent.contains(b));
        System.out.println("adjacentOverlap=" + first.overlaps(adjacent));
        System.out.println("crossingOverlap=" + first.overlaps(crossing));
        System.out.println("mayStart=" + may.fromInclusive());
        System.out.println("mayEndExclusive=" + may.untilExclusive());
        System.out.println("springDayHours=" + Duration.between(
                spring.fromInclusive(), spring.untilExclusive()).toHours());
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 HalfOpenValidity.java
java HalfOpenValidity
```

Stdout:

```text
activeAtStart=true
activeAtEnd=false
adjacentActiveAtBoundary=true
adjacentOverlap=false
crossingOverlap=true
mayStart=2024-04-30T17:00:00Z
mayEndExclusive=2024-05-31T17:00:00Z
springDayHours=23
PASS checks=24
```

The `eq` helper actively throws `AssertionError` on mismatch, so the `-ea` flag is not required. The `rejects` helper verifies that intervals outside the contract are rejected.

The test cases cover:

- Immediately before, at, and immediately after the start bound.
- Immediately before, at, and immediately after the end bound.
- Two adjacent intervals.
- Two overlapping intervals and symmetry of the overlap check.
- Exact boundary intersection.
- Identical intervals.
- Fixed `Clock` at both boundaries.
- Equal bounds or reversed-order bounds.
- Inclusive end date converted to an exclusive instant bound.
- A business day whose length is not 24 hours.

One nanosecond before/after is used to test `Instant` boundaries in memory. That does not require the data store to support nanosecond precision; integration tests should choose values matching the store's actual precision.

## 9. Keep the same convention when querying and storing

For events belonging to an interval, the illustrative SQL condition is:

```sql
WHERE event_time >= :from_inclusive
  AND event_time <  :until_exclusive
```

For validity-interval records active at an instant:

```sql
WHERE valid_from <= :reference_time
  AND :reference_time < valid_until
```

These are the condition shapes; actual parameter syntax depends on the API and database engine. Parameters must be bound with proper instant semantics rather than concatenating display strings into SQL.

Do not change the condition above to an inclusive end-bound check while keeping the name `untilExclusive`. Java, queries, stored data, and the UI must agree on the meaning.

If the store reduces the precision of the bounds, define the truncation/rounding rule and re-verify instants near the boundary. The half-open convention solves inclusivity; it does not prevent the store from altering bound values.

When exposing an API, names such as `fromInclusive` and `untilExclusive` keep callers from having to guess. For screens using "through end of day", convert at the UI boundary as shown rather than forcing users to understand a technical timestamp.

## 10. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Excluding both start and end bounds | Not valid at the exact start time | Include the start bound |
| Including the end bound | Two adjacent intervals both claim the boundary | Use `t < until` |
| Creating a gap by adding/subtracting one small unit | Depends on precision | Share the half-open boundary |
| Comparing date-time strings | Wrong ordering or lost information | Compare appropriate temporal types |
| Treating `!contains` as always expired | Confuses not-started with expired | Distinguish the three states |
| Not validating bound order | Invalid intervals get stored | Validate on creation |
| Taking the last day at 23:59:59 | Drops fractional seconds | Use the start of the next day as the exclusive bound |
| Always adding a fixed 24 hours for every day | Wrong when offset changes | Compute from the next calendar date and zone |
| Java and SQL using two different conventions | Inconsistent check results | Document and verify the same contract |

## 11. Practice exercises with expected results

### Exercise 1: Boundary point of two versions

A has interval `[09:00, 10:00)`, B has interval `[10:00, 11:00)`.

- At exactly 10:00: A is not valid, B is valid.
- The two intervals do not overlap.
- No need to subtract one millisecond from A's end bound.

### Exercise 2: Finding the intersection

A is `[09:00, 10:00)`, B is `[09:30, 11:00)`.

The intersection must be `[09:30, 10:00)`. Exactly 10:00 does not belong to the intersection.

### Exercise 3: Invalid interval

Create an interval whose two bounds are both 09:00. Per the program's contract, the operation must raise an error. Explain the difference between "an empty interval that can be defined mathematically" and "a validity interval accepted by this model".

### Exercise 4: Single-day filter

The user selects only 2024-05-01. The end bound must be the start of 2024-05-02 in the chosen zone. An event at the exact end bound must not be counted in 2024-05-01.

### Exercise 5: Unbounded end

Design a model that allows no end bound. Specify how it handles containing an instant, overlapping, and representing missing data. Do not just pass `null` into the existing `Window` and expect the methods to handle it automatically.

A correct half-open interval requires three consistent things: the start bound is included, the end bound is excluded, and every processing layer uses that same meaning. Test cases at the exact boundaries are the most important evidence.
