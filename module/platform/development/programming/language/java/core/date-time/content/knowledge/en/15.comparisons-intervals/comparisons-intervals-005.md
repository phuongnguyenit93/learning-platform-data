# Closed, Open, and Half-Open Interval Conventions in Java Date-Time

When describing a time interval, it is necessary to clearly specify **which endpoints are included in the interval**. Two intervals with the same start and end values but using different conventions can contain different points in time. This convention affects membership checks, merging adjacent intervals, overlap detection, database queries, and avoiding double-counting events at boundaries.

In mathematics:

- **Closed interval** `[a, b]`: includes both the start point `a` and the end point `b`.
- **Open interval** `(a, b)`: excludes both endpoints.
- **Left-open, right-closed (half-open)** `(a, b]`: excludes `a`, includes `b`.
- **Left-closed, right-open (half-open)** `[a, b)`: includes `a`, excludes `b`.

In software, the **`[start, end)` — start-inclusive, end-exclusive** convention is usually the most convenient choice. The start point is included, while the end point belongs to the next interval (if any), not the current one.

## 1. Conditions for Determining Interval Membership

| Notation | Start | End | Condition for instant `t` |
| --- | --- | --- | --- |
| `[a, b]` | Inclusive | Inclusive | `a <= t && t <= b` |
| `(a, b)` | Exclusive | Exclusive | `a < t && t < b` |
| `(a, b]` | Exclusive | Inclusive | `a < t && t <= b` |
| `[a, b)` | Inclusive | Exclusive | `a <= t && t < b` |

The operators in the table express the concept. For Java types such as `Instant`, `LocalDateTime`, or `LocalDate`, use `isBefore`, `isAfter`, `equals`, or `compareTo` for comparison.

For example, the interval `[09:00, 10:00)` contains 09:00, but does not contain 10:00. When placing the next interval `[10:00, 11:00)` adjacent to it, the point 10:00 belongs only to the second interval. Conversely, if both intervals were closed at the 10:00 boundary, an event occurring at that exact time could be counted twice.

You should not represent "end of day" using an assumed timestamp like `23:59:59.999`: data may have microsecond or nanosecond resolution. Instead, represent the boundary using the **start of the next day, exclusive**.

## 2. Why Is `[start, end)` Useful?

Consider two adjacent intervals:

```text
A = [09:00, 10:00)
B = [10:00, 11:00)

A: 09:00 <= t < 10:00
B: 10:00 <= t < 11:00
```

The point 10:00 does not belong to A, but belongs to B. There is no gap and no double-counting at the boundary.

Benefits:

1. **Contiguous merging:** `[a,b)` and `[b,c)` merge into `[a,c)`.
2. **No double-counting:** each boundary point belongs to at most one adjacent interval.
3. **Length without offset:** `Duration.between(start, end)` already measures the distance between two points; there is no need to add one nanosecond even though the end is excluded.
4. **Clear empty interval:** `[a,a)` contains no elements.
5. **Query compatibility:** `timestamp >= start AND timestamp < end` does not depend on the smallest resolution the database can store.

For example, hourly intervals in a day can be represented contiguously as `[09:00, 10:00)`, `[10:00, 11:00)`, `[11:00, 12:00)`. This convention does not depend on whether timestamps are stored to millisecond or nanosecond precision.

## 3. Membership Checks in Java

With `Instant`, a half-open interval membership check can be written as:

```java
static boolean containsHalfOpen(Instant start, Instant end, Instant t) {
    return !t.isBefore(start) && t.isBefore(end);
}
```

- `!t.isBefore(start)` is equivalent to `t >= start`.
- `t.isBefore(end)` is equivalent to `t < end`.

You should validate the order of the endpoints. If a non-empty interval is required, enforce `start.isBefore(end)`. If empty intervals are allowed, `start.equals(end)` means no point in time is contained in `[start,end)`. If `start.isAfter(end)`, reject the input rather than silently swapping the two endpoints.

Methods for other conventions:

```java
static boolean containsClosed(Instant start, Instant end, Instant t) {
    return !t.isBefore(start) && !t.isAfter(end);
}

static boolean containsOpen(Instant start, Instant end, Instant t) {
    return t.isAfter(start) && t.isBefore(end);
}

static boolean containsOpenClosed(Instant start, Instant end, Instant t) {
    return t.isAfter(start) && !t.isAfter(end);
}
```

These are **illustrative method snippets**; they need to be placed inside a Java class with `import java.time.Instant;`. Use method names that clearly reflect the convention so callers do not accidentally use a closed interval when the API contract specifies a half-open interval.

## 4. Detecting Overlap Between Two Intervals

Assume both intervals are valid and half-open:

- A = `[aStart, aEnd)`
- B = `[bStart, bEnd)`

They overlap if and only if:

```text
aStart < bEnd && bStart < aEnd
```

In Java:

```java
static boolean overlapsHalfOpen(
        Instant aStart, Instant aEnd,
        Instant bStart, Instant bEnd) {
    return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
}
```

This formula assumes each interval has already been validated with `start <= end`. Empty intervals should be handled according to an explicit policy; do not let overlap-checking logic silently accept inverted-endpoint intervals.

| A | B | Overlap? | Why |
| --- | --- | --- | --- |
| `[09:00, 10:00)` | `[10:00, 11:00)` | No | 10:00 is excluded at the end of A and included at the start of B |
| `[09:00, 10:00)` | `[09:30, 10:30)` | Yes | Both contain a shared segment of time |
| `[09:00, 10:00)` | `[08:00, 09:00)` | No | 09:00 is excluded from B |
| `[09:00, 10:00)` | `[09:00, 10:00)` | Yes | The two intervals coincide |
| `[10:00, 10:00)` | `[09:00, 11:00)` | No | The first interval is empty |

For two closed intervals, the boundary rule changes: `[09:00,10:00]` and `[10:00,11:00]` share the point 10:00. Therefore, do not use the half-open overlap formula if the data uses a different endpoint convention.

## 5. Measuring Distance vs. Checking Membership

For two instants, `Duration.between(start, end)` computes the distance on the timeline:

```java
Duration duration = Duration.between(start, end);
```

Do not add one nanosecond to "include end". Whether an endpoint belongs to an interval is a **membership** convention; `Duration` measures the distance between two points. If `end` is before `start`, `Duration` can be negative, so validate the order beforehand if the business logic requires a non-negative duration.

Do not equate timeline distance with the number of calendar days. For global events, use `Instant`. For calendar dates, use `LocalDate`. For local schedules in a time zone, create start and end instants using the same `ZoneId`; DST can make a local day 23 or 25 hours long.

## 6. Calendar Date Ranges and Data Queries

Suppose you need all events on 2026-10-24 in UTC. Create the start of the day and the start of the next day:

```java
LocalDate day = LocalDate.of(2026, 10, 24);
ZoneId zone = ZoneOffset.UTC;

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
```

The query interval is `[start,end)`. For another zone, such as `America/New_York`, compute both instants from that same `ZoneId`; do not assume a local day is always 86,400 seconds.

Corresponding query:

```sql
SELECT *
FROM events
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant;
```

This approach includes records at the exact start of the day, excludes records at the exact start of the next day, and avoids constructing `23:59:59.999999999`.

If the UI lets users select both the start date and end date **inclusively**, for example October 24 to October 26, you can convert the end date into an exclusive boundary:

```java
LocalDate first = LocalDate.of(2026, 10, 24);
LocalDate lastInclusive = LocalDate.of(2026, 10, 26);
LocalDate endExclusive = lastInclusive.plusDays(1);
// Date range: [2026-10-24, 2026-10-27)
```

This is a conversion on `LocalDate`. If `lastInclusive` is `LocalDate.MAX`, `plusDays(1)` exceeds the representable range and throws an exception; handle that case separately if the application supports maximum bounds. Do not replace it with an assumed millisecond or nanosecond "end-of-day timestamp".

## 7. How Time Zones and DST Affect Boundaries

With `LocalDate`, a calendar date is a calendar unit. When you need to turn local dates into instants, a time zone is required:

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDate day = LocalDate.of(2024, 3, 10);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

System.out.println(Duration.between(start, end).toHours()); // 23
```

March 10, 2024 in New York is the start of DST, so the range from the start of that day to the start of the next day is 23 hours on the timeline. On a fall-back day, the range can be 25 hours long. Using a half-open interval remains correct: the start-of-next-day boundaries connect seamlessly, even when the actual duration is not 24 hours.

Do not replace `end` with `start.plus(Duration.ofDays(1))` when the requirement is "the start of the next local calendar day". `Duration.ofDays(1)` is 86,400 seconds; `day.plusDays(1).atStartOfDay(zone)` follows the calendar and zone rules.

For scheduled appointments in a zone with DST gaps or overlaps, a policy for resolving nonexistent or ambiguous local times still needs to be defined. The half-open interval convention only specifies endpoint inclusion; it does not by itself resolve how an ambiguous `LocalDateTime` is converted into an instant.

## 8. Choosing the Right Convention

| Use Case | Common Convention | Reason |
| --- | --- | --- |
| Adjacent log or event buckets | `[start,end)` | No boundary overlap |
| Querying all records in a day | `[startOfDay,nextStartOfDay)` | Independent of timestamp resolution |
| Booking schedules and conflict checks | `[start,end)` if the contract defines end time as available | Two consecutive bookings can touch without overlapping |
| Representing a mathematically closed range | `[a,b]` | When the end point truly belongs to the value set |
| Range excluding both ends | `(a,b)` | Used when business rules explicitly require exclusive endpoints |
| Reports where the user selects an inclusive end date | Convert to start of next day as end-exclusive | Avoids assumed end-of-day values |

Booking example: if a meeting ends at 10:00 and the next one starts at 10:00, the `[start,end)` model treats the two schedules as non-overlapping. If the business requires a 10-minute cleanup buffer between bookings, add the buffer as an explicit rule rather than inconsistently changing the endpoint convention.

## 9. Standalone Runnable Java 17+ Example

Create a file named **`IntervalConventionDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;

public class IntervalConventionDemo {
    static boolean containsHalfOpen(
            Instant start, Instant end, Instant t) {
        return !t.isBefore(start) && t.isBefore(end);
    }

    static boolean overlapsHalfOpen(
            Instant aStart, Instant aEnd,
            Instant bStart, Instant bEnd) {
        return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
    }

    static boolean validHalfOpen(Instant start, Instant end) {
        return !start.isAfter(end);
    }

    public static void main(String[] args) {
        Instant nine = Instant.parse("2026-10-24T09:00:00Z");
        Instant ten = Instant.parse("2026-10-24T10:00:00Z");
        Instant eleven = Instant.parse("2026-10-24T11:00:00Z");
        Instant nineThirty = Instant.parse("2026-10-24T09:30:00Z");

        System.out.println("contains start = "
                + containsHalfOpen(nine, ten, nine));
        System.out.println("contains end = "
                + containsHalfOpen(nine, ten, ten));
        System.out.println("adjacent overlap = "
                + overlapsHalfOpen(nine, ten, ten, eleven));
        System.out.println("partial overlap = "
                + overlapsHalfOpen(nine, ten, nineThirty, eleven));
        System.out.println("empty interval valid = "
                + validHalfOpen(ten, ten));
        System.out.println("empty interval contains point = "
                + containsHalfOpen(ten, ten, ten));
        System.out.println("duration hours = "
                + Duration.between(nine, ten).toHours());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac IntervalConventionDemo.java
java IntervalConventionDemo
```

Output:

```text
contains start = true
contains end = false
adjacent overlap = false
partial overlap = true
empty interval valid = true
empty interval contains point = false
duration hours = 1
```

The code uses fixed instants, so it does not depend on the current clock or default time zone. The interval `[10:00,10:00)` is considered valid but empty; if business rules forbid empty intervals, require `start.isBefore(end)`.

## 10. Common Pitfalls

| Pitfall | Consequence | Correct Approach |
| --- | --- | --- |
| Using `timestamp <= end` for all intervals | Boundary events may be counted twice | Standardize on `[start,end)` when appropriate for the domain |
| Using `23:59:59.999` as end of day | Misses timestamps with higher precision | Use the start of the next day as `endExclusive` |
| Using `start.plus(Duration.ofDays(1))` for the next local day | Wrong across DST transitions | Compute the next day using the calendar and the same `ZoneId` |
| Forgetting to validate endpoint order | Inverted intervals can produce confusing results | Check `start <= end` before using |
| Treating `[a,a]` and `[a,a)` as the same | Closed interval contains `a`, half-open is empty | Document the convention clearly in the API |
| Adding one nanosecond to include `end` | Precision-dependent and error-prone | Define the endpoint convention rather than offsetting by a unit |
| Using `LocalDateTime` as an absolute instant | Missing offset/zone | Resolve with a `ZoneId` or known offset |
| Using the overlap formula without validating intervals | Hides inverted or empty intervals | Validate endpoints and interval rules |
| Merging two adjacent closed intervals | Boundary point is duplicated | Use half-open intervals for contiguous partitions |
| Assuming a local day is always 24 hours | Fails during DST | Compute duration from resolved instants |

## 11. Checklist and Self-Check

Before designing an API or query, define the endpoint convention; choose the right temporal type; validate endpoints; test immediately before, exactly at, and immediately after each boundary; compute local days with a `ZoneId` when needed; and apply the same policy consistently across the API, database, reports, and UI.

**Self-check questions**

1. For `[09:00,10:00)`, is 09:00 included? → Yes.
2. Is 10:00 included? → No.
3. Do `[09:00,10:00)` and `[10:00,11:00)` overlap? → No.
4. Should end of day be set to `23:59:59.999999999`? → Usually no; use the start of the next day as the exclusive boundary.
5. Does `Duration.between(start,end)` add a nanosecond because the interval is half-open? → No.
6. How should a local day range in New York be computed? → From the start of the day and the start of the next day in `America/New_York`, then converted to `Instant`.
7. Does the empty interval `[a,a)` contain `a`? → No.
8. Why should a shared convention be explicitly documented? → So application layers do not double-count, miss boundaries, or interpret endpoints differently.

### Java API Documentation

- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): comparing points in time and representing timestamps.
- [Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): measuring the distance between instants.
- [Java SE 17 — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): calendar date operations.
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): local date-time with time zone and DST rules.

**Key takeaway:** `[start,end)` is start-inclusive and end-exclusive. This convention enables non-overlapping contiguous partitions, resolution-independent timestamp queries, and a clear representation of empty intervals. Keep calendar date ranges separate from absolute timeline durations.
