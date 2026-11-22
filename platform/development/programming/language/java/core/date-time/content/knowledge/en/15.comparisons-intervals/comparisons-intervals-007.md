# Detecting Overlaps, Adjacency, and Gaps

When comparing two time intervals, it is necessary to distinguish three relationships: **overlap** (*overlap/intersection*), **adjacency** (*adjacent/touching*), and **having a gap in between** (*gap*). Two intervals may sit right next to each other without sharing any instant; they may partially overlap; or there may be an uncovered span of time between them.

Java provides types such as `Instant`, `LocalDateTime`, `ZonedDateTime`, and `Duration`, but there is no general-purpose `Interval` class in `java.time`. Typically, you represent an interval by **a start bound and an end bound**, and then define comparison rules that fit your domain.

This lesson uses half-open intervals `[start, end)`: **inclusive of start, exclusive of end**. This convention is useful for booking schedules, work shifts, validity periods, and consecutive intervals.

## 1. Start and End Conventions

The interval `[10:00, 11:00)` includes every instant from 10:00 onward, but **excludes 11:00 itself**. Therefore:

- `[10:00, 11:00)` and `[11:00, 12:00)` are adjacent.
- They do not overlap, because the first interval does not contain 11:00 while the second starts at 11:00.
- Merging two consecutive intervals produces `[10:00, 12:00)`, with no gap and no double-counting of the boundary point.

| Notation | Meaning |
| --- | --- |
| `[a, b)` | Includes a, excludes b |
| `[a, b]` | Includes both a and b |
| `(a, b)` | Excludes both a and b |
| `max(startA, startB)` | Start of the intersection |
| `min(endA, endB)` | End of the intersection |

For schedules measured in minutes or nanoseconds, `[start, end)` avoids having to manually find the "last nanosecond" of an interval. The important thing is to use a consistent convention across data, algorithms, and APIs.

## 2. How Do Overlap, Adjacency, and Gap Differ?

Suppose A = `[10:00, 11:00)`:

| Interval B | Relationship | Positive intersection? | Gap? |
| --- | --- | --- | --- |
| `[10:30, 11:30)` | Partial overlap | Yes, 10:30–11:00 | No |
| `[10:00, 11:00)` | Exact match | Yes, all of A | No |
| `[11:00, 12:00)` | Adjacent | No | No |
| `[12:00, 13:00)` | Disjoint, B is after | No | Yes: 11:00–12:00 |
| `[09:00, 10:00)` | Adjacent before | No | No |
| `[08:00, 09:00)` | Disjoint, B is before | No | Yes: 09:00–10:00 |
| `[10:15, 10:45)` | B is inside A | Yes, all of B | No |
| `[10:00, 10:00)` | Empty interval | No | Requires separate convention |

**Gap** here means the span of time between two disjoint intervals, not a zero-length interval. The interval `[t, t)` is an empty interval under the half-open model: it covers no instant.

## 3. Overlap Formula for Half-Open Intervals

Given A = `[startA, endA)` and B = `[startB, endB)`. Two intervals overlap with positive length when:

```text
startA < endB && startB < endA
```

The first condition states that A starts before B ends; the second states that B starts before A ends. If either is missing, one interval lies completely to the left/right of the other, or the two intervals are merely adjacent.

The intersection, if any:

```text
intersectionStart = max(startA, startB)
intersectionEnd   = min(endA, endB)

If intersectionStart < intersectionEnd:
    intersection = [intersectionStart, intersectionEnd)
Else:
    no positive-length intersection
```

For example, A = `[10:00, 11:00)` and B = `[10:30, 11:30)`. The intersection start is max(10:00, 10:30) = 10:30; the intersection end is min(11:00, 11:30) = 11:00. The intersection has a length of 30 minutes.

If `intersectionStart == intersectionEnd`, they do not overlap with positive length; a common case is two adjacent intervals. Do not use `<=` instead of `<` if you need to detect the intersection of half-open intervals.

## 4. Validating Intervals Before Comparing

A normal interval must satisfy `start <= end`:

- `start < end`: non-empty interval.
- `start == end`: empty interval under the `[start, end)` convention.
- `start > end`: invalid interval; should be rejected or normalized using an explicit business rule.

Do not automatically swap start and end for all inputs. If the data is erroneous like `[13:00, 12:00)`, swapping it to `[12:00, 13:00)` hides the source bug. For overnight shifts, store the actual start date and end date; do not assume an end hour smaller than the start hour always means valid data.

Use `Instant` if both bounds are absolute points in time. `LocalDateTime` only holds a calendar date and wall-clock time, and does not define a point on the timeline without a zone/offset. Choose the type based on the data's semantics before comparing.

## 5. Comparing Using Instant

For events that have occurred, exact deadlines, or global validity, `Instant` is usually appropriate:

```java
import java.time.Instant;

Instant startA = Instant.parse("2024-01-01T10:00:00Z");
Instant endA = Instant.parse("2024-01-01T11:00:00Z");
Instant startB = Instant.parse("2024-01-01T10:30:00Z");
Instant endB = Instant.parse("2024-01-01T11:30:00Z");

boolean overlaps =
        startA.isBefore(endB) && startB.isBefore(endA);
// true
```

This is an illustrative snippet meant to be placed inside a Java method. `isBefore` and `isAfter` compare instants without converting to strings. Avoid comparing arbitrary timestamp strings: differing formats and offsets can cause lexicographical order not to reflect chronological order.

`Instant` does not carry a display time zone. When you need to present a timestamp locally, convert each bound to `ZonedDateTime`; however, use the underlying `Instant` values for real-time comparisons.

## 6. Adjacency and Gaps

For two non-empty intervals, adjacency occurs when one's end bound equals the other's start bound:

```text
endA == startB || endB == startA
```

Under the half-open convention, valid intervals sharing a boundary like this do not overlap. If A precedes B and `endA < startB`, then the gap is:

```text
gap = [endA, startB)
gapDuration = startB - endA
```

Only produce a gap under the strict condition `endA < startB`. If they are equal, the two intervals are adjacent and the gap has length 0; if `endA > startB`, they may overlap.

| A | B | Result |
| --- | --- | --- |
| `[10:00, 11:00)` | `[11:00, 12:00)` | Adjacent, no gap |
| `[10:00, 11:00)` | `[11:15, 12:00)` | Gap `[11:00, 11:15)`, 15 minutes |
| `[10:00, 11:00)` | `[10:30, 12:00)` | Overlapping, no gap |
| `[12:00, 13:00)` | `[10:00, 11:00)` | Gap `[11:00, 12:00)` |

The algorithm should determine which interval ends first so that the returned gap is in chronological order, regardless of argument order. If two intervals overlap or are adjacent, there is no positive gap.

## 7. Complete Java 17+ Example: overlap, intersection, touches, and gap

Java has no general-purpose `Interval` class in `java.time`. This example uses a record holding two `Instant`s and defines behavior for half-open intervals `[start, end)`.

Save the file **`IntervalRelationsDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

public class IntervalRelationsDemo {
    record Interval(Instant start, Instant end) {
        Interval {
            if (start == null || end == null) {
                throw new IllegalArgumentException("Bounds must not be null");
            }
            if (end.isBefore(start)) {
                throw new IllegalArgumentException("End must not precede start");
            }
        }

        boolean isEmpty() {
            return start.equals(end);
        }

        boolean overlaps(Interval other) {
            return !isEmpty() && !other.isEmpty()
                    && start.isBefore(other.end) && other.start.isBefore(end);
        }

        boolean touches(Interval other) {
            return !isEmpty() && !other.isEmpty() && !overlaps(other)
                    && (end.equals(other.start) || other.end.equals(start));
        }

        Optional<Interval> intersection(Interval other) {
            Instant from = start.isAfter(other.start) ? start : other.start;
            Instant to = end.isBefore(other.end) ? end : other.end;
            return from.isBefore(to)
                    ? Optional.of(new Interval(from, to))
                    : Optional.empty();
        }

        Optional<Interval> gapTo(Interval other) {
            if (isEmpty() || other.isEmpty() || overlaps(other) || touches(other)) {
                return Optional.empty();
            }
            if (end.isBefore(other.start)) {
                return Optional.of(new Interval(end, other.start));
            }
            if (other.end.isBefore(start)) {
                return Optional.of(new Interval(other.end, start));
            }
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2024-01-01T10:00:00Z");
        Interval a = new Interval(t0, t0.plusSeconds(3600));
        Interval overlap = new Interval(t0.plusSeconds(1800), t0.plusSeconds(5400));
        Interval adjacent = new Interval(t0.plusSeconds(3600), t0.plusSeconds(7200));
        Interval apart = new Interval(t0.plusSeconds(9000), t0.plusSeconds(10800));

        System.out.println("A overlaps B: " + a.overlaps(overlap));
        System.out.println("A intersection B: " + a.intersection(overlap).orElseThrow());
        System.out.println("A touches adjacent: " + a.touches(adjacent));
        System.out.println("A overlaps adjacent: " + a.overlaps(adjacent));
        System.out.println("A gap to apart: " + a.gapTo(apart).orElseThrow());

        Interval intersection = a.intersection(overlap).orElseThrow();
        System.out.println("Intersection duration: "
                + Duration.between(intersection.start(), intersection.end()).toMinutes()
                + " minutes");

        Interval empty = new Interval(t0, t0);
        System.out.println("Zero-length interval empty: " + empty.isEmpty());
        System.out.println("Zero-length interval overlaps A: " + empty.overlaps(a));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac IntervalRelationsDemo.java
java IntervalRelationsDemo
```

**Exact stdout**, verified with Java 17:

```text
A overlaps B: true
A intersection B: Interval[start=2024-01-01T10:30:00Z, end=2024-01-01T11:00:00Z]
A touches adjacent: true
A overlaps adjacent: false
A gap to apart: Optional[Interval[start=2024-01-01T11:00:00Z, end=2024-01-01T12:30:00Z]]
Intersection duration: 30 minutes
Zero-length interval empty: true
Zero-length interval overlaps A: false
```

### Reading the Output and Implementation

- The record constructor checks that both bounds are non-null and rejects cases where end precedes start.
- `overlaps` requires both intervals to be non-empty and uses two strict `isBefore` comparisons. Therefore, merely touching at a boundary is not an overlap.
- `intersection` picks the larger start and the smaller end; it only returns an interval if the intersection start is before the intersection end. If there is no positive intersection, it returns `Optional.empty()`.
- `touches` detects two non-empty intervals that have an equal boundary without overlapping.
- `gapTo` only returns an interval between two disjoint, non-empty intervals. The gap is returned in chronological order, even if the other interval is passed first.
- `Duration.between` measures the length of the intersection; in the example, 10:30–11:00 is 30 minutes long.

Because the example uses `Instant`, interval relationships do not depend on display zone or DST. For bookings in local time, resolve times with a `ZoneId`/offset according to business policy before comparing real instants.

## 8. Empty Intervals and Checking Whether an Instant Lies Inside an Interval

The interval `[t, t)` has length 0 and contains no instants. If the application does not allow empty intervals, reject `start == end` right in the constructor rather than allowing it and handling it in many places.

For a half-open interval, an instant lies inside the interval when:

```java
boolean contains(Instant instant) {
    return !instant.isBefore(start) && instant.isBefore(end);
}
```

This is an illustrative method body inside the `Interval` record. The condition is equivalent to `start <= instant && instant < end`. If you switch to a closed-both-ends convention `[start, end]`, the formula and the notion of adjacency must be redefined; you cannot copy half-open formulas without changing the comparisons.

Note that an empty interval may numerically fall inside a larger interval, yet under the half-open convention it still contains no instants and does not overlap with another interval. The example code intentionally treats empty intervals as not overlapping, touching, or forming gaps.

## 9. Local Time, Time Zones, and DST

If the problem is "the meeting room is booked from 01:30 to 03:30 in New York", the input might be `LocalDateTime`, but a `ZoneId` is needed to convert it to instants on the timeline:

```java
import java.time.*;

ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime startLocal = LocalDateTime.of(2024, 3, 10, 1, 30);
LocalDateTime endLocal = LocalDateTime.of(2024, 3, 10, 3, 30);

Instant start = startLocal.atZone(newYork).toInstant();
Instant end = endLocal.atZone(newYork).toInstant();

Duration elapsed = Duration.between(start, end);
System.out.println(elapsed.toMinutes()); // 60
```

On 2024-03-10, New York begins DST and skips 02:00–02:59. The wall clock from 01:30 to 03:30 shows two hours, but the actual elapsed time is only 60 minutes. This is why you **should not simply subtract local times** to measure real duration across DST.

There are also local times that do not exist or are repeated during DST transitions. For appointments or bookings, decide whether gaps/overlaps are rejected, automatically adjusted, or require user selection. Once each bound has been resolved to an `Instant`, the overlap/touch/gap formulas accurately reflect relationships on the timeline.

## 10. Practical Applications

### Detecting Overlapping Bookings

For room or equipment bookings, two intervals `[startA, endA)` and `[startB, endB)` conflict when:

```text
startA < endB && startB < endA
```

Bookings 10:00–11:00 and 11:00–12:00 do not conflict. Booking 10:30–11:30 against 10:00–11:00 has a 30-minute overlap.

### Finding Gaps Between Schedules

Sort intervals by their start bound. Track the furthest end bound seen among processed intervals. If the next interval starts after this bound, the span between the two bounds is a gap; if the next interval starts before this bound, they overlap/cover each other.

When merging multiple intervals, update the end bound using `max(endSoFar, currentEnd)`. If a new interval is completely nested inside an already-processed interval and you set the bound to `currentEnd` alone, the algorithm will forget the tail that is still covered.

### Record Validity Periods

Validity can be represented as `[validFrom, validTo)`. Two consecutive versions are adjacent when `previous.validTo == next.validFrom`. If two intervals overlap, two records may be valid at the same time; if there is a gap, no record covers that span. Clearly define the bound convention in the schema or API contract.

## 11. Common Mistakes

1. **Using `<=` in the half-open overlap formula.** Two adjacent intervals are mistakenly treated as overlapping.
2. **Inconsistent start/end conventions.** `[start, end)` and `[start, end]` yield different boundary results.
3. **Ignoring empty intervals.** `[t, t)` has no positive intersection; check separately if allowed to exist.
4. **Treating overlap and touches as the same relationship.** Two separate conditions must be defined.
5. **Creating a gap while intervals still overlap.** Only create a gap when one interval ends strictly before the other starts.
6. **Allowing end before start.** Reject invalid data or apply a documented rule; do not silently swap bounds.
7. **Comparing local date-time strings from different time zones.** Resolve to `Instant` first if relationships on the real timeline are needed.
8. **Using LocalDateTime to measure true duration without a zone.** DST can create non-existent or repeated times.
9. **Failing to handle nested intervals when merging schedules.** Keep the maximum end bound covered so far.
10. **Treating adjacency as a positive gap.** Equal boundaries mean adjacency, with zero empty duration.

## 12. Essential Tests

| Case | A | B | Expected |
| --- | --- | --- | --- |
| Partial overlap | `[10:00, 11:00)` | `[10:30, 11:30)` | Intersection `[10:30, 11:00)` |
| B inside A | `[10:00, 12:00)` | `[10:30, 11:00)` | Intersection equals B |
| Exact match | `[10:00, 11:00)` | `[10:00, 11:00)` | Intersection equals both |
| Adjacent | `[10:00, 11:00)` | `[11:00, 12:00)` | No overlap; touches true |
| Positive gap | `[10:00, 11:00)` | `[11:15, 12:00)` | Gap `[11:00, 11:15)` |
| Reversed order | `[12:00, 13:00)` | `[10:00, 11:00)` | Gap `[11:00, 12:00)` |
| Empty interval | `[10:00, 10:00)` | `[09:00, 11:00)` | No overlap |
| Invalid interval | `[11:00, 10:00)` | Any | Constructor rejects |
| DST New York | 01:30–03:30 on 2024-03-10 | — | Actual duration 60 minutes after zone resolution |
| Shared boundary | `[a,b)` | `[b,c)` | No shared instant |

In JUnit, use `assertTrue`/`assertFalse` for relationships, `assertEquals` to compare expected intersections/gaps, and `assertThrows` to verify that end before start is rejected. Tests should cover equal boundaries, empty intervals, nested intervals, and both argument orders.

## 13. Choosing the Right Representation

| Need | Choice |
| --- | --- |
| Real-time interval | Two `Instant`s |
| Measure intersection length | `Duration.between(intersection.start(), intersection.end())` |
| Calendar time at a location | `LocalDateTime` + `ZoneId`, DST-resolved |
| Calendar date interval | Two `LocalDate`s with clear bound convention |
| Check overlap of half-open intervals | `startA < endB && startB < endA` and non-empty intervals |
| Check adjacency | `endA == startB` or `endB == startA` |
| Compute gap | Earlier interval ends strictly before later interval starts |
| Actual duration | `Duration.between(startInstant, endInstant)` |

**Key takeaway:** For half-open intervals `[start, end)`, two intervals overlap with positive length when `startA < endB && startB < endA`. Adjacency means sharing a boundary without overlapping; a gap exists only when two intervals are disjoint with a positive span between them. Validate intervals, keep bound conventions consistent, and use `Instant` when relationships on the real timeline are needed.
