# Epoch and Pre-Epoch / Post-Epoch Timestamps in Java

In date-time programming, a *timestamp* refers to a point in time on the timeline. For two systems to exchange and compare points in time independently of how dates and times are displayed, they typically count time from a conventional reference point: the **epoch**.

## 1. What Is the Epoch?

The **Unix epoch / Java epoch** is **1970-01-01T00:00:00Z**, i.e., 00:00:00 on January 1, 1970 in UTC. The letter `Z` in ISO 8601 denotes UTC, equivalent to a `+00:00` offset.

- **At the epoch**: timestamp equals `0`.
- **After the epoch**: positive timestamp.
- **Before the epoch**: negative timestamp. Negative values are valid and do not automatically mean invalid data.
- **The unit is part of the data contract**: `-1` second, `-1` millisecond, and `-1` microsecond represent three different points in time.

~~~text
                        epoch
 ... 1969-12-31           1970-01-01             1970-01-02 ...
         before <-------------|-------------> after
  negative epoch second       0        positive epoch second
~~~

The epoch is **not Java's release date**, not local time, and does not automatically change with the machine's time zone. Only the representation or interpretation of a date and time in a given time zone changes.

**Distinction:** *epoch* is the origin reference point; *epoch second* is the number of seconds from the epoch; *epoch millisecond* is the number of milliseconds from the epoch; *timestamp* is a value representing a point in time, which may be numeric or a date-time string with time zone information.

## 2. A Few Points in Time Right Around the Epoch

| UTC Instant | Epoch seconds (integer part) | Epoch milliseconds |
|---|---:|---:|
| `1969-12-31T23:59:59Z` | `-1` | `-1000` |
| `1969-12-31T23:59:59.999Z` | `-1` | `-1` |
| `1970-01-01T00:00:00Z` | `0` | `0` |
| `1970-01-01T00:00:00.001Z` | `0` | `1` |
| `1970-01-01T00:00:01Z` | `1` | `1000` |

For `1969-12-31T23:59:59.999Z`, the distance to the epoch is only **1 millisecond**, so epoch milliseconds equals `-1`. Meanwhile, Java's split of an instant into *epoch seconds* and *nano-of-second* yields `-1` second plus `999_000_000` nanoseconds: `-1 + 0.999 = -0.001` seconds. The integer seconds part uses floor rounding along the timeline, not truncation toward 0.

### Common Units

| Unit | Common Notation | Per Second |
|---|---|---:|
| Second | `epochSeconds`, Unix time | `1` |
| Millisecond | `epochMillis` | `1_000` |
| Microsecond | `epochMicros` | `1_000_000` |
| Nanosecond | `epochNanos` | `1_000_000_000` |

A field name like `timestamp` **does not indicate the unit**. You must confirm it from the API contract, database documentation, storage format, or data type. Do not guess the unit just by counting digits, especially for timestamps before the epoch or very far from the epoch.

## 3. Representing Points in Time with `java.time.Instant`

In Java 17+, `Instant` represents **a point on the timeline**, not tied directly to local time. It is the appropriate type for record creation times, event occurrences, audit logs, and time comparisons.

Key APIs:

| Need | API | Meaning |
|---|---|---|
| Get standard epoch | `Instant.EPOCH` | `1970-01-01T00:00:00Z` |
| From seconds | `Instant.ofEpochSecond(seconds)` | Constructs an `Instant` from seconds |
| From seconds and nanos | `Instant.ofEpochSecond(seconds, nanoAdjustment)` | Adds sub-second precision, auto-normalizes |
| From milliseconds | `Instant.ofEpochMilli(millis)` | Accepts pre-/post-epoch values, including negative ones |
| Get seconds | `instant.getEpochSecond()` | The second of the one-second interval containing `instant` |
| Get nano-of-second | `instant.getNano()` | Always in `0..999_999_999` |
| Get milliseconds | `instant.toEpochMilli()` | Epoch milliseconds value; loses sub-1 ms precision |
| Parse ISO 8601 | `Instant.parse("1969-12-31T23:59:59Z")` | String must include appropriate offset/UTC |
| Compare | `isBefore`, `isAfter`, `compareTo` | Compares by actual point in time |
| Compute distance | `Duration.between(a, b)` | Duration from `a` to `b` |

Conceptually, `Instant` consists of `long epochSecond` and `int nanoOfSecond`. For example:

~~~text
Instant: 1969-12-31T23:59:59.500Z
epochSecond = -1
nanoOfSecond = 500_000_000
total seconds relative to epoch = -0.5 s
~~~

This explains why you cannot use ordinary integer division `-1 / 1000` and treat it as the epoch second: Java's integer division rounds **toward 0**, giving `0`, whereas the second containing `-1 ms` must be `-1`.

`Instant.ofEpochSecond` can accept a `nanoAdjustment` that is negative or exceeds one billion and **normalizes** `getNano()` to be within `0..999_999_999`. For example, `Instant.ofEpochSecond(0, -1_000_000)` is equal to `Instant.ofEpochMilli(-1)`.

## 4. Standalone Java 17 Example

Create the file **`EpochDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public class EpochDemo {
    public static void main(String[] args) {
        Instant before = Instant.parse("1969-12-31T23:59:59.999Z");
        Instant epoch = Instant.EPOCH;
        Instant after = Instant.parse("1970-01-01T00:00:00.001Z");

        System.out.println("before ms = " + before.toEpochMilli());
        System.out.println("epoch ms = " + epoch.toEpochMilli());
        System.out.println("after ms = " + after.toEpochMilli());
        System.out.println("before seconds = " + before.getEpochSecond());
        System.out.println("before nanos = " + before.getNano());

        System.out.println("from -1 ms = " + Instant.ofEpochMilli(-1));
        System.out.println("from -0.5 s = "
                + Instant.ofEpochSecond(-1, 500_000_000));
        System.out.println("distance = "
                + Duration.between(before, after).toMillis() + " ms");

        System.out.println("epoch in +07:00 = "
                + epoch.atOffset(ZoneOffset.ofHours(7)));

        LocalDateTime local = LocalDateTime.of(1970, 1, 1, 0, 0);
        System.out.println("local with UTC = "
                + local.toEpochSecond(ZoneOffset.UTC));
        System.out.println("local with +07:00 = "
                + local.toEpochSecond(ZoneOffset.ofHours(7)));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac EpochDemo.java
java EpochDemo
~~~

Verified output when compiled with `--release 17`:

~~~text
before ms = -1
epoch ms = 0
after ms = 1
before seconds = -1
before nanos = 999000000
from -1 ms = 1969-12-31T23:59:59.999Z
from -0.5 s = 1969-12-31T23:59:59.500Z
distance = 2 ms
epoch in +07:00 = 1970-01-01T07:00+07:00
local with UTC = 0
local with +07:00 = -25200
~~~

**Explanation:** `before` and `after` lie on opposite sides of the epoch, 2 ms apart. `-1 ms` is normalized by Java into `-1 epoch second` plus `999_000_000 ns`. Converting the epoch to the `+07:00` offset only changes the **display representation** to 07:00, not the timestamp `0`. Conversely, when *interpreting* the same `LocalDateTime` 00:00 at `+07:00`, the actual instant corresponds to `1969-12-31T17:00:00Z`, i.e., `-25_200` seconds relative to the epoch.

## 5. Epoch and Time Zones: Two Different Questions

Distinguish between:

1. **When did the event occur?** Use `Instant` or a timestamp with a unit: the answer can be compared across machines and time zones.
2. **What does the local clock show?** Combine `Instant` with `ZoneId` (a time zone with historical/DST rules) or `ZoneOffset` (a fixed offset).

For example, **the same point in time**:

~~~text
1970-01-01T00:00:00Z       (UTC)
1970-01-01T07:00:00+07:00  (+07:00 offset)
epoch milliseconds = 0     (both)
~~~

`LocalDateTime` only has year, month, day, hour, minute, and second; it **does not store a time zone or offset**. Therefore, a unique epoch timestamp cannot be derived from a `LocalDateTime` without knowing how to interpret its offset or `ZoneId`. Similarly, `LocalDate` only represents a calendar date; to find the start of the day, you must specify a time zone, and in some regions with clock changes, the start of the day is not necessarily 00:00.

When working with a real location, prefer `ZoneId.of("Asia/Ho_Chi_Minh")` or an appropriate region ID because historical rules may differ from the current offset. The `+07:00` example above is a **fixed offset** for easy-to-verify calculation; do not assume a geographical region always had that offset at every point in history.

## 6. Handling Negative Timestamps and Safe Unit Conversion

For negative millisecond timestamps, using `Instant.ofEpochMilli(...)` is direct and safe. If you need to **split** milliseconds into seconds + nanos, use `Math.floorDiv` and `Math.floorMod` to keep the remainder non-negative.

The following snippet is **illustrative code placed inside a method**, not a standalone Java file:

~~~java
long epochMillis = -1L;
long seconds = Math.floorDiv(epochMillis, 1_000L);    // -1
long millisInSecond = Math.floorMod(epochMillis, 1_000L); // 999
Instant restored = Instant.ofEpochSecond(
        seconds, millisInSecond * 1_000_000L);
// restored = 1969-12-31T23:59:59.999Z
~~~

Similarly, if an API provides **microseconds**:

~~~java
long epochMicros = -1L;
long seconds = Math.floorDiv(epochMicros, 1_000_000L);
long microsInSecond = Math.floorMod(epochMicros, 1_000_000L);
Instant instant = Instant.ofEpochSecond(
        seconds, microsInSecond * 1_000L);
// instant = 1969-12-31T23:59:59.999999Z
~~~

If you need to convert from `Instant` back to microseconds, compute it with overflow checking, e.g. `Math.addExact(Math.multiplyExact(instant.getEpochSecond(), 1_000_000L), instant.getNano() / 1_000)`. This expression floors to microseconds along the timeline; sub-microsecond data is lost. When converting to milliseconds, `toEpochMilli()` also reduces precision. For very distant timestamps, converting to `long` milliseconds/microseconds can overflow and throw `ArithmeticException`.

**Avoid naive division/multiplication tricks:** `-1 / 1000 == 0` in Java, and `0 * 1000` cannot recover `-1 ms`; the remainder `-1 % 1000 == -1` is also not a valid nano-of-second for `Instant`. Use the built-in APIs or `floorDiv`/`floorMod` when you must split units manually.

## 7. Practical Application and Data Validation

### Exchanging via API or Storing in a Database

- For an event occurrence time, you can transmit ISO 8601 with an explicit offset, such as `"1969-12-31T23:59:59.999Z"`, and parse it into `Instant`.
- If transmitting integers, the contract must state the **unit**, e.g. `createdAtEpochMillis: -1`; do not name it generically `createdAt: -1` if the receiver does not know the unit.
- Java's `long` type is standard for epoch seconds/millis. For pre-1970 data, the database, JSON schema, and frontend must accept **negative numbers**; do not automatically treat every negative timestamp as an error.
- Store `Instant`/UTC for actual points in time when appropriate; apply time zones for presentation according to user needs. Pure dates such as birth dates or calendar expiration dates should consider `LocalDate` instead of forcing them into timestamps.
- Historical pre-epoch data can appear in birth dates, archived events, legacy system imports, and backfills; test data across all three cases: **negative, zero, and positive**.

### Common Pitfalls

| Pitfall | Why It's Wrong / How to Fix |
|---|---|
| Treating negative numbers as invalid | Negative timestamps represent points in time before 1970-01-01 UTC; only reject when the data contract genuinely forbids them |
| Mixing seconds and milliseconds | `Instant.ofEpochSecond(-1)` is 1 second before the epoch, while `ofEpochMilli(-1)` is 1 millisecond before the epoch |
| Integer division on negative timestamps | `-1 / 1000 = 0`; use `Instant.ofEpochMilli` or `Math.floorDiv`/`floorMod` |
| Assuming `getNano()` is negative before the epoch | `getNano()` is always `0..999_999_999`; the sign is on `getEpochSecond()` |
| Attaching the machine's default time zone to UTC values | Causes hour shifts; parse explicit offsets and use `Instant` when storing points in time |
| Converting `LocalDateTime` to epoch without an offset | A local time value can correspond to different instants; requires `ZoneId`/`ZoneOffset` |
| Using `int` for epoch milliseconds | `int` range is too small; use `long` and check contracts across systems |
| Thinking `toEpochMilli()` preserves nanoseconds | Sub-1 ms precision is lost; keep `Instant` if nanoseconds are needed |
| Relying on `System.nanoTime()` as a Unix timestamp | `nanoTime()` is for measuring elapsed time with an arbitrary origin, not the 1970 epoch |
| Assuming the OS wall clock always advances steadily | `Instant.now()`/`currentTimeMillis()` follow the wall clock and can jump; to measure task duration, use `System.nanoTime()` |

## 8. Self-Check Questions

1. What are the epoch seconds of `1969-12-31T23:59:59Z`? **`-1`**, because it is exactly one second earlier than the epoch.
2. What does `Instant.ofEpochMilli(-1).getNano()` return? **`999_000_000`**; the accompanying epoch second is `-1`.
3. Do the two strings `1970-01-01T00:00:00Z` and `1970-01-01T07:00:00+07:00` have the same timestamp? **Yes**, both represent epoch `0`.
4. Is `LocalDateTime.of(1970, 1, 1, 0, 0)` guaranteed to be epoch `0`? **No**; in UTC it is `0`, while in `+07:00` it is `-25_200` seconds.
5. If you receive `-1` from an API, is that enough to know the point in time? **No**, you must confirm the unit (seconds, milliseconds, microseconds, etc.) and the meaning of the field.

**Key takeaway:** The epoch is fixed at `1970-01-01T00:00:00Z`; before the epoch timestamps are negative, after the epoch they are positive. In Java, prefer `Instant` for actual points in time, always identify the right unit, and handle negative fractions using `Instant`'s normalization rules.

### References

- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — `java.time` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
