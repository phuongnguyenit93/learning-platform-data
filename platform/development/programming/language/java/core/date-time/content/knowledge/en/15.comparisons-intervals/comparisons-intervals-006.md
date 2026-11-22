# Checking Whether an Instant Falls Within an Interval

`Instant` represents a specific point on the timeline. To check whether `point` lies between `start` and `end`, compare the `Instant` values using `isBefore()`, `isAfter()`, and `equals()`. There is no need to convert timestamps to strings or manually subtract milliseconds for comparison.

First, define the **boundary convention**. The half-open interval `[start, end)` is usually well suited for logs, data queries, and time windows: it includes the start instant and excludes the exact end instant.

## 1. Instant Is a Point in Time; Duration Is a Length of Time

| Type | Meaning | Example |
|---|---|---|
| `Instant` | An absolute point on the timeline. | Event at `2024-06-01T12:00:00Z`. |
| `Duration` | Amount of time between two points. | 30 minutes or `Duration.between(start, end)`. |
| `LocalDateTime` | Local date and time without an offset/zone. | `2024-06-01T19:00` is not enough to identify an instant. |
| `ZonedDateTime` | Date and time interpreted according to `ZoneId` rules. | Displaying an instant in Hanoi/New York. |

If you already have an `Instant`, compare it directly against bounds that are also `Instant`. The two strings `2024-06-01T12:00:00Z` and `2024-06-01T19:00:00+07:00` represent the same instant, even though they are written differently. Do not compare timestamp strings with different formats or offsets; parse them into `Instant` first.

`Instant` retains nanosecond precision in the Java model. If you only compare `getEpochSecond()`, two instants with the same second but different nanoseconds will be treated as equal unintentionally. Use the direct comparison methods to preserve precision.

## 2. The Half-Open Interval [start, end)

The interval `[start, end)` contains the start point and every point after it, up to **before** the end bound:

~~~text
start <= point < end
~~~

Java condition:

~~~java
boolean contains = !point.isBefore(start) && point.isBefore(end);
~~~

`!point.isBefore(start)` means `point >= start`. `point.isBefore(end)` means the point must be earlier than the end bound. Therefore:

| Test point | In `[12:00, 12:30)`? | Reason |
|---|---|---|
| 11:59:59.999999999 | No | Earlier than start. |
| 12:00:00 | Yes | Start bound is included. |
| 12:15:00 | Yes | Inside the interval. |
| 12:29:59.999999999 | Yes | Still before end. |
| 12:30:00 | No | End bound is excluded. |
| 12:30:00.000000001 | No | Later than end. |

Half-open intervals are very useful when chaining windows: `[10:00, 11:00)` and `[11:00, 12:00)`. The 11:00 instant is excluded from the first interval and belongs to the second, so it is neither double-counted nor skipped.

## 3. Four Common Boundary Conventions

| Convention | Java condition | start equals point | end equals point |
|---|---|---|---|
| Closed `[start, end]` | `!point.isBefore(start) && !point.isAfter(end)` | Yes | Yes |
| Open `(start, end)` | `point.isAfter(start) && point.isBefore(end)` | No | No |
| Open-closed `(start, end]` | `point.isAfter(start) && !point.isAfter(end)` | No | Yes |
| Half-open `[start, end)` | `!point.isBefore(start) && point.isBefore(end)` | Yes | No |

Both `isBefore()` and `isAfter()` return `false` when two instants are equal. Therefore, to include a bound, you typically negate the opposite comparison. Do not write `point.isAfter(start)` if the actual requirement is for `point` to be greater than **or equal to** `start`.

The following illustrative methods demonstrate each convention:

~~~java
static boolean containsHalfOpen(Instant p, Instant s, Instant e) {
    return !p.isBefore(s) && p.isBefore(e);
}

static boolean containsClosed(Instant p, Instant s, Instant e) {
    return !p.isBefore(s) && !p.isAfter(e);
}

static boolean containsOpen(Instant p, Instant s, Instant e) {
    return p.isAfter(s) && p.isBefore(e);
}

static boolean containsOpenClosed(Instant p, Instant s, Instant e) {
    return p.isAfter(s) && !p.isAfter(e);
}
~~~

These are illustrative methods that require importing `java.time.Instant` and placing them inside a class. Reflect the boundary convention in the method name or Javadoc, and avoid an ambiguous `contains` method.

## 4. Runnable Java 17+ Example: Exact Boundary Checks

Save the file `InstantRangeDemo.java`:

~~~java
import java.time.Instant;

public class InstantRangeDemo {
    static boolean containsHalfOpen(Instant point, Instant start, Instant end) {
        return !point.isBefore(start) && point.isBefore(end);
    }

    static boolean containsClosed(Instant point, Instant start, Instant end) {
        return !point.isBefore(start) && !point.isAfter(end);
    }

    static boolean containsOpen(Instant point, Instant start, Instant end) {
        return point.isAfter(start) && point.isBefore(end);
    }

    static boolean containsOpenClosed(Instant point, Instant start, Instant end) {
        return point.isAfter(start) && !point.isAfter(end);
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2024-06-01T12:00:00Z");
        Instant end = Instant.parse("2024-06-01T12:30:00Z");

        Instant before = start.minusNanos(1);
        Instant atStart = start;
        Instant middle = Instant.parse("2024-06-01T12:15:00Z");
        Instant atEnd = end;
        Instant after = end.plusNanos(1);

        System.out.println("Half-open before: " + containsHalfOpen(before, start, end));
        System.out.println("Half-open at start: " + containsHalfOpen(atStart, start, end));
        System.out.println("Half-open middle: " + containsHalfOpen(middle, start, end));
        System.out.println("Half-open at end: " + containsHalfOpen(atEnd, start, end));
        System.out.println("Half-open after: " + containsHalfOpen(after, start, end));
        System.out.println("Closed at end: " + containsClosed(atEnd, start, end));
        System.out.println("Open at start: " + containsOpen(atStart, start, end));
        System.out.println("Open-closed at end: " + containsOpenClosed(atEnd, start, end));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac InstantRangeDemo.java
java InstantRangeDemo
~~~

Stdout:

~~~text
Half-open before: false
Half-open at start: true
Half-open middle: true
Half-open at end: false
Half-open after: false
Closed at end: true
Open at start: false
Open-closed at end: true
~~~

The instants are created deterministically using `Instant.parse`, `minusNanos(1)`, and `plusNanos(1)`, so the output is deterministic and does not depend on the default timezone or the real clock.

## 5. Validating start, end, and null

Before checking containment, clearly decide what to do if `start` is after `end`. An interval with `start > end` is usually invalid input, so reject it rather than silently swapping the bounds:

~~~java
if (start.isAfter(end)) {
    throw new IllegalArgumentException("start must not be after end");
}
~~~

This is illustrative code that requires `start` and `end`. If `start.equals(end)`, the interval `[start, end)` is empty: no point is both greater than or equal to `start` and less than `end`. By contrast, the closed interval `[start, end]` with equal bounds contains exactly one point.

Comparison methods throw `NullPointerException` if the target object is `null`. Applications should choose a consistent contract: treat parameters as required and reject early, or explicitly define that a null point means `false`. Do not let behavior vary across methods.

Example of strict validation:

~~~java
static boolean containsHalfOpen(Instant point, Instant start, Instant end) {
    if (point == null || start == null || end == null) {
        throw new IllegalArgumentException("point/start/end are required");
    }
    if (start.isAfter(end)) {
        throw new IllegalArgumentException("start must not be after end");
    }
    return !point.isBefore(start) && point.isBefore(end);
}
~~~

This is an alternative version of the method with the same name in the previous example; do not paste both versions into the same class. `Objects.requireNonNull` is also suitable if the desired contract is to throw `NullPointerException`.

## 6. Comparing Instant Instead of Strings or Local Time

`Instant.compareTo(other)` can be used to sort points in time; `isBefore` and `isAfter` usually express conditions more clearly.

Avoid the following mistakes:

- Comparing timestamp strings with different formats or UTC offsets.
- Comparing local hours/minutes alone, ignoring date and zone.
- Converting down to epoch milliseconds when business logic must distinguish nanoseconds.
- Using `LocalDateTime` as an absolute point in time even though it carries no offset/zone.

Example of two representations of the same instant:

~~~java
Instant utc = Instant.parse("2024-06-01T12:00:00Z");
Instant withOffset = Instant.parse("2024-06-01T19:00:00+07:00");

System.out.println(utc.equals(withOffset));
System.out.println(utc.isBefore(withOffset));
System.out.println(utc.isAfter(withOffset));
~~~

This is illustrative code. Output:

~~~text
true
false
false
~~~

`equals` is true because both strings refer to the same instant. `isBefore` and `isAfter` are both false when they are equal.

## 7. Applications to Queries, Expiration, and Local Dates

### Log queries and pagination

The half-open interval `[from, until)` works well for queries:

~~~sql
SELECT *
FROM events
WHERE occurred_at >= :fromInstant
  AND occurred_at <  :untilInstant
ORDER BY occurred_at, event_id;
~~~

This is illustrative SQL; bind parameters and use a column type matching the database's timestamp convention. This approach avoids duplicating events right on the boundary when stitching consecutive windows together. If multiple events share the same timestamp, use a secondary key such as `event_id` for a stable pagination order.

### Expiration

If `createdAt` is the start instant and `expiresAt` is the expiration instant, the common half-open convention is:

~~~java
boolean active = !now.isBefore(createdAt) && now.isBefore(expiresAt);
boolean expired = !now.isBefore(expiresAt);
~~~

At the exact `expiresAt`, the item has already expired. Using only `now.isAfter(expiresAt)` to determine expiration misses the exact expiration instant. In security systems, the time source must be trustworthy and checks should run server-side; a correct interval condition alone does not handle clock skew or race conditions.

### Events belonging to a day in a timezone

If you need events for a local date, first determine the two boundaries according to `ZoneId`:

~~~java
Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

This is illustrative code that requires declaring `LocalDate date` and `ZoneId zone`. Then filter by `[from, until)`. Do not replace this with `from.plus(Duration.ofHours(24))` because a day in a DST zone can be 23 or 25 hours long; day boundaries also depend on zone rules.

### Duration does not replace boundary rules

`Duration.between(start, point)` gives the signed duration from `start` to `point`. However, to determine whether `point` is still inside the interval or past `end`, you still need to consider `end` and the boundary convention. Direct `Instant` comparisons usually make the condition's intent easier to read.

## 8. Intersection of Two Intervals

For two valid half-open intervals `A = [aStart, aEnd)` and `B = [bStart, bEnd)`, they overlap when:

~~~java
boolean overlaps =
        aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
~~~

This is illustrative code, assuming each interval has been validated with `start <= end`. Two intervals that only touch at a boundary — such as `[10:00, 11:00)` and `[11:00, 12:00)` — do not overlap because 11:00 is excluded from the first interval.

The intersection of two valid intervals has:

~~~text
intersectionStart = max(aStart, bStart)
intersectionEnd   = min(aEnd, bEnd)

They overlap if intersectionStart < intersectionEnd.
~~~

For example, `A = [10:00, 12:00)` and `B = [11:00, 13:00)` yield the intersection `[11:00, 12:00)`. If the intersection's start bound equals its end bound, the intersection is empty.

### Java 17+ Example: Interval

Save `InstantIntervalsDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;

public class InstantIntervalsDemo {
    record Interval(Instant start, Instant end) {
        Interval {
            if (start == null || end == null) {
                throw new IllegalArgumentException("bounds are required");
            }
            if (start.isAfter(end)) {
                throw new IllegalArgumentException("start after end");
            }
        }

        boolean contains(Instant point) {
            return point != null
                    && !point.isBefore(start)
                    && point.isBefore(end);
        }

        boolean isEmpty() {
            return start.equals(end);
        }

        boolean overlaps(Interval other) {
            return start.isBefore(other.end)
                    && other.start.isBefore(end);
        }

        Interval intersection(Interval other) {
            if (!overlaps(other)) {
                return null;
            }
            Instant s = start.isAfter(other.start) ? start : other.start;
            Instant e = end.isBefore(other.end) ? end : other.end;
            return new Interval(s, e);
        }
    }

    public static void main(String[] args) {
        Interval a = new Interval(
                Instant.parse("2024-06-01T10:00:00Z"),
                Instant.parse("2024-06-01T12:00:00Z"));
        Interval b = new Interval(
                Instant.parse("2024-06-01T11:00:00Z"),
                Instant.parse("2024-06-01T13:00:00Z"));
        Interval touching = new Interval(
                Instant.parse("2024-06-01T12:00:00Z"),
                Instant.parse("2024-06-01T14:00:00Z"));

        Instant atStart = a.start();
        Instant atEnd = a.end();
        Interval common = a.intersection(b);

        System.out.println("Contains start: " + a.contains(atStart));
        System.out.println("Contains end: " + a.contains(atEnd));
        System.out.println("A overlaps B: " + a.overlaps(b));
        System.out.println("A overlaps touching: " + a.overlaps(touching));
        System.out.println("Intersection: " + common);
        System.out.println("Intersection seconds: "
                + Duration.between(common.start(), common.end()).toSeconds());
        System.out.println("Empty [x,x): "
                + new Interval(atStart, atStart).isEmpty());
    }
}
~~~

Compile and run:

~~~bash
javac InstantIntervalsDemo.java
java InstantIntervalsDemo
~~~

Stdout:

~~~text
Contains start: true
Contains end: false
A overlaps B: true
A overlaps touching: false
Intersection: Interval[start=2024-06-01T11:00:00Z, end=2024-06-01T12:00:00Z]
Intersection seconds: 3600
Empty [x,x): true
~~~

In the example, the `record` has a compact constructor that validates the bounds. `intersection` returns `null` when there is no overlap; real applications can use `Optional<Interval>` to represent a potentially absent result. `contains` returns false if `point` is null, while null bounds are rejected in the constructor — this is the specific contract of the example.

## 9. Current Clock and Clock Skew

To check against the current time, use `Instant.now()`; in business code, injecting a `Clock` allows unit tests to fix the reference point:

~~~java
Instant now = clock.instant();
boolean active = !now.isBefore(start) && now.isBefore(end);
~~~

This is illustrative code that requires declaring `Clock clock`. Capturing a single `now` value and reusing it throughout a decision makes the result more consistent than reading the clock multiple times.

`Instant` identifies a point, but timestamps do not guarantee an absolutely accurate physical clock. In distributed systems, clocks on two servers can drift; events may appear in a timestamp order that does not reflect true causality. For security expirations and concurrent operations, you need an authoritative time source, clock skew controls, and appropriate transactional condition checks.

Use `Clock.fixed` in tests to control time; there is no need for `Thread.sleep`. You can construct points right around the boundary using `end.minusNanos(1)`, `end`, and `end.plusNanos(1)`.

## 10. Common Mistakes

| Mistake | Consequence | Correct approach |
|---|---|---|
| Using `point.isAfter(start)` when you want to include `start`. | A point equal to `start` is excluded. | Use `!point.isBefore(start)`. |
| Using `!point.isAfter(end)` for a half-open interval. | A point equal to `end` is mistakenly included. | Use `point.isBefore(end)`. |
| Using `now.isAfter(expiresAt)` to determine expiration. | An instant equal to `expiresAt` is not treated as expired. | Use `!now.isBefore(expiresAt)`. |
| Comparing timestamp strings. | Different formats and offsets can cause wrong ordering. | Parse into `Instant`. |
| Comparing only epoch seconds. | Ignores nanosecond differences. | Use `Instant.isBefore/isAfter/equals`. |
| Adding 24 hours to find the start of the next day in a zone. | Wrong on DST days or special zone rule changes. | Use `atStartOfDay(zone)` for both days. |
| Ignoring `start` after `end`. | Nonsensical interval or unexpected conditions. | Validate ordering before use. |
| Using timestamps as the sole causal order. | Clock skew or duplicate timestamps invert the order. | Use sequence/version/ID if needed. |
| Reading the current time multiple times for one decision. | The value changes between reads. | Capture `now` once. |

## 11. Self-Check Questions

**1.** For `[start, end)`, does a point equal to `start` belong to the interval?

**Answer:** Yes. The condition `!point.isBefore(start)` allows equality with the start bound.

**2.** For `[start, end)`, does a point equal to `end` belong to the interval?

**Answer:** No. The end bound is excluded so consecutive windows do not double-count.

**3.** Do `[10:00, 11:00)` and `[11:00, 12:00)` overlap?

**Answer:** No. The 11:00 instant is excluded from the first interval and included in the second.

**4.** Why is `isAfter()` not enough to check whether `point` is greater than or equal to `start`?

**Answer:** It returns false when the two values are equal. Use `!point.isBefore(start)` or combine `isAfter` with `equals`.

**5.** Why should you avoid using timestamp strings to check intervals?

**Answer:** Strings may lack offsets or have different formats. Use `Instant` to compare absolute points in time.

**6.** If `start` equals `end`, does `[start, end)` contain any point?

**Answer:** No. That is an empty interval; a closed-interval convention would have a different meaning.

## Takeaways

Before implementing a check, decide which bounds are included. For the half-open interval `[start, end)`, the condition is `!point.isBefore(start) && point.isBefore(end)`. Comparing with `Instant` preserves the timeline and nanosecond precision; validate bound ordering, define null behavior, and use the same convention across code, database queries, expiration checks, and tests.
