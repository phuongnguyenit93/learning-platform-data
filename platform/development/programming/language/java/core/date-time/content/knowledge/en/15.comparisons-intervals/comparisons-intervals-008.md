# Representing a Full Day Using Start of Day to Start of Next Day

When you need to filter or process an entire calendar day, the safe approach is to represent that day as a **half-open** interval: from the start of the target day, inclusive, to the start of the next day, exclusive. In Java, use `LocalDate` and `ZoneId` to find both boundaries and then convert them to `Instant` when querying timestamps.

The interval is represented as:

```text
[startOfDay, startOfNextDay)
```

This corresponds to the query condition:

```sql
created_at >= :startInclusive
AND created_at <  :endExclusive
```

This approach avoids manually constructing a `23:59:59.999` boundary, does not depend on whether timestamp precision is seconds, milliseconds, or nanoseconds, and correctly handles 23- or 25-hour days when a time zone observes Daylight Saving Time (DST).

## 1. Definition of a Half-Open Interval

A half-open interval `[start, end)` has two rules:

- **Start inclusive:** a value equal to `start` belongs to the interval.
- **End exclusive:** a value equal to `end` does not belong to the interval.

For the calendar date `2026-05-10`, we define:

```text
[start of 2026-05-10, start of 2026-05-11)
```

An event at the exact start of May 10 is included; an event at the exact start of May 11 belongs to the next day. Two consecutive days form two non-overlapping yet contiguous intervals:

```text
Day D:     [start(D),     start(D + 1))
Day D + 1: [start(D + 1), start(D + 2))
```

The `start(D + 1)` instant serves as both the end of the first day and the start of the second day. There is no need to add or subtract one millisecond to avoid duplicate records.

## 2. Why Not Use 23:59:59.999?

Approaches such as `timestamp <= 23:59:59.999` carry several risks:

1. **Variable precision:** a database may store microseconds or nanoseconds; an event occurring after the `.999` millisecond but still within the same day can be missed.
2. **Hard to apply across multiple consecutive days:** you must calculate the end-of-day instant according to each system's specific precision.
3. **Assumes every day is 24 hours long:** in a DST-observing zone, a local day can be 23 or 25 actual hours long.
4. **Hard to compose intervals:** half-open intervals are easy to merge, paginate, and split without duplicating or skipping boundaries.

Use `>= startInclusive` and `< endExclusive` instead of `BETWEEN start AND 23:59:59.999`. In SQL, `BETWEEN` is typically inclusive on both ends, so care is needed when using it for day boundaries.

## 3. Creating Day Boundaries in Java

`LocalDate` represents a calendar date without a time or time zone. `ZoneId` provides the zone rules. Use `LocalDate.atStartOfDay(zone)` to find the valid start-of-day instant in that zone, then convert it to `Instant`:

```java
LocalDate date = LocalDate.of(2026, 5, 10);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive = date.atStartOfDay(zone).toInstant();
Instant endExclusive = date.plusDays(1).atStartOfDay(zone).toInstant();
```

This snippet requires imports from `java.time`. It is important to add **one calendar day** with `date.plusDays(1)` and then recompute the start of day in the zone; do not use `startInclusive.plus(Duration.ofHours(24))` as the next day's boundary.

`atStartOfDay(zone)` returns the earliest valid start-of-day time according to the zone's rules. In most zones, that time is `00:00`. However, historical time-zone transitions can occur right at midnight, making the actual start time different from `00:00`; the API follows the zone rules instead of making a fixed assumption.

## 4. Complete Program: Computing the Interval for a Day

Create the file **`LocalDayWindowDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class LocalDayWindowDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate date = LocalDate.of(2026, 5, 10);

        Instant startInclusive = date.atStartOfDay(zone).toInstant();
        Instant endExclusive = date.plusDays(1)
                .atStartOfDay(zone)
                .toInstant();

        System.out.println("Zone: " + zone);
        System.out.println("Start inclusive: " + startInclusive);
        System.out.println("End exclusive: " + endExclusive);
        System.out.println("Duration hours: "
                + java.time.Duration.between(startInclusive, endExclusive).toHours());
    }
}
```

Compile and run with Java 17+:

```bash
javac LocalDayWindowDemo.java
java LocalDayWindowDemo
```

Output:

```text
Zone: Asia/Ho_Chi_Minh
Start inclusive: 2026-05-09T17:00:00Z
End exclusive: 2026-05-10T17:00:00Z
Duration hours: 24
```

Vietnam uses UTC+07:00 at this example date. The start of May 10 in Vietnam corresponds to 17:00 UTC on May 9; the start of May 11 corresponds to 17:00 UTC on May 10. Boundaries are computed from the date and zone, not from an end-of-day time string.

## 5. Using Half-Open Intervals in Data Queries

When timestamps are stored as instants, compute both boundaries in the business time zone and use a half-open condition. For example, with Spring Data or JDBC, you can pass two `Instant` parameters to the query:

```sql
SELECT id, created_at, amount
FROM orders
WHERE created_at >= :startInclusive
  AND created_at < :endExclusive
ORDER BY created_at, id
```

`startInclusive` and `endExclusive` are computed in Java as shown in the previous section. Parameter names should be bound safely through the database API; never concatenate input strings into SQL.

Benefits of half-open intervals:

- **No day overlap:** a record at the exact new-day boundary does not belong to the previous day.
- **No missed valid timestamps:** every value less than the next boundary is covered.
- **Easy time-based pagination:** the next page can start directly at the previous page's `endExclusive`.
- **Works at any precision:** no need to guess the last representable timestamp in the database.

If filtering on a `DATE` column that stores only a calendar date, querying by date directly is usually more appropriate. Half-open `Instant` intervals are especially useful when the column holds an actual instant, such as `created_at`.

## 6. DST: A Local Day Is Not Always 24 Hours Long

In regions with Daylight Saving Time, clocks can jump forward or backward. A local day can be 23 or 25 actual hours long. Therefore, day boundaries must be computed from `LocalDate` and `ZoneId`; do not define the start of the next day by adding a fixed 24 actual hours.

The program **`DstDayWindowDemo.java`** demonstrates the DST transition dates in New York in 2026:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class DstDayWindowDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        showDay(zone, LocalDate.of(2026, 3, 8));
        showDay(zone, LocalDate.of(2026, 11, 1));
    }

    private static void showDay(ZoneId zone, LocalDate date) {
        Instant start = date.atStartOfDay(zone).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
        long hours = Duration.between(start, end).toHours();

        System.out.println(date + ": " + start + " -> " + end
                + ", hours=" + hours);
    }
}
```

Run:

```bash
javac DstDayWindowDemo.java
java DstDayWindowDemo
```

Output according to New York time-zone rules in 2026:

```text
2026-03-08: 2026-03-08T05:00:00Z -> 2026-03-09T04:00:00Z, hours=23
2026-11-01: 2026-11-01T04:00:00Z -> 2026-11-02T05:00:00Z, hours=25
```

On March 8, New York springs forward from standard time to daylight time; one local hour does not exist, and the day is only 23 hours long. On November 1, clocks fall back and the local hour 01:00–01:59 occurs twice; the day is 25 hours long.

Even though the durations of these two days differ from 24 hours, both intervals are exact for the **entire local calendar day** when boundaries are computed with `atStartOfDay(zone)`. Using `start.plus(Duration.ofHours(24))` could end the interval incorrectly in the middle of a calendar day.

## 7. Choosing the Right Zone: User or Business?

Decide which zone defines the day before constructing the interval:

- **Personal calendar:** use the user's selected time zone.
- **Branch reports or end-of-day closing:** use the `ZoneId` configured for that branch or market.
- **Technical UTC day:** use UTC when the target is genuinely a UTC day.
- **Dates stored in a `DATE` column:** keep the `LocalDate` value; do not turn a pure date into a timestamp if the domain does not need an instant.

For example, a transaction created at `2026-05-10T01:00:00Z` may still be on May 9 in California while already on May 10 in Vietnam. If a report closes on California time, use the California zone to compute `startInclusive` and `endExclusive`; the time zone of the device running the report should not alter business results.

## 8. Adding Calendar Days vs. Adding Elapsed Duration

The following two expressions have different meanings:

```java
LocalDate tomorrow = date.plusDays(1);
Instant after24Hours = start.plus(java.time.Duration.ofHours(24));
```

- `date.plusDays(1)` advances to the next calendar day. To convert that date to an instant in a zone, use `tomorrow.atStartOfDay(zone)`.
- `start.plus(Duration.ofHours(24))` moves forward by exactly 24 hours on the timeline from a known instant.

On an ordinary day, the two results may match. Across a DST transition or another time-zone change, they can differ. Rule of thumb: **use date and zone arithmetic for local calendars; use `Instant` and `Duration` for absolute elapsed time**.

## 9. Interval Boundaries and Common Mistakes

| Incorrect Approach | Problem | Correct Approach |
| --- | --- | --- |
| Using `23:59:59.999` as end of day | Can miss timestamps with higher precision | Use the start of the next day, exclusive |
| Using `BETWEEN start AND end` with `end` as start of next day | Includes records at the exact next-day boundary in SQL where `BETWEEN` is inclusive on both ends | `>= start AND < end` |
| Adding 24 hours to start of day | Wrong on 23- or 25-hour days | Compute `date.plusDays(1).atStartOfDay(zone)` |
| Using the server's time zone for branch reports | Results depend on the runtime environment | Use an explicitly configured business time zone |
| Converting via `LocalDateTime` and assuming it is an instant | Loses offset and zone | Store/pass `Instant`, use `ZoneId` when creating boundaries |
| Assuming start of day is always `00:00` everywhere | Historical zone rules include transitions at midnight | Use `LocalDate.atStartOfDay(zone)` |
| Not testing boundaries | Misses exact `end` instants or duplicates records | Test start inclusive, end exclusive, and two adjacent intervals |
| Counting both endpoints when consecutive days are needed | Two intervals can both include events at the boundary | Use the half-open convention consistently |

## 10. Testing Boundaries

At a minimum, test the following cases:

1. A timestamp equal to `startInclusive` is included in the results.
2. A timestamp one database-supported precision unit less than `endExclusive` is still included.
3. A timestamp equal to `endExclusive` is not counted in the previous day.
4. Two intervals for two consecutive days do not overlap and leave no gap at the boundary.
5. A 23- or 25-hour DST day still spans from start of day to start of next day.
6. A user's time zone differs from the business zone, yet reports still follow the chosen business zone.
7. The database and driver preserve accurate round-trips for both `Instant` values without losing precision at the endpoints.

You can test continuity by verifying that `endExclusive(day)` equals `startInclusive(day.plusDays(1))` when using the same `ZoneId`. This is the key property of the half-open interval model.

### Key Takeaway

To represent a calendar day, use the interval **`[startOfDay, startOfNextDay)`**. Compute both boundaries with `LocalDate.atStartOfDay(zone)`, then convert to `Instant` to query timestamps using `>= start` and `< end`. This avoids precision bugs, prevents duplicate records across days, and respects the DST rules of the chosen time zone.
