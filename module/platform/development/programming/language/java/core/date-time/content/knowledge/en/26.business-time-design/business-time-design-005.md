# Expiration Boundary Convention: Inclusive or Exclusive Endpoint

## 1. Is it still usable at the exact expiration time?

Suppose access has an end boundary of `10:15:00Z`. Comparing at `10:14:59Z` or `10:15:01Z` is usually straightforward; bugs tend to hide at **exact `10:15:00Z`**. There are two contracts that can both be expressed clearly:

- **Exclusive endpoint:** at the end boundary, it has already expired.
- **Inclusive endpoint:** at the exact end boundary, it is still valid; it only expires once past it.

Java does not choose a business contract on behalf of the application. You need to agree on it before writing operators, queries, and user-facing messages.

## 2. Expressing the contract as a time interval

Let `start` be the start point and `end` be the end boundary. If the start point is included:

| Interval | Valid when | At exact `now == end` |
| --- | --- | --- |
| `[start, end)` | `start <= now && now < end` | Expired |
| `[start, end]` | `start <= now && now <= end` | Still valid |

The brackets `[`/`]` mean the boundary point is included; the parentheses `(`/`)` mean the boundary point is excluded. When talking only about expiration, remember there is also the condition before the start time: "not yet expired" is not synonymous with "currently valid."

The half-open interval `[start, end)` is often convenient for schedules and data: two intervals `[A, B)` and `[B, C)` do not overlap, nor do they leave a gap at point B. If both ends are closed, point B can belong to both intervals. This is a modeling benefit, not a mandatory rule for every business domain.

## 3. Representing with Instant and comparison methods

For global timestamps, use `Instant` to avoid display time zones affecting comparisons. Both `isBefore` and `isAfter` are strict comparisons: when two instants are equal, both return `false`.

| End boundary contract | Not yet expired | Expired |
| --- | --- | --- |
| Exclude `end` | `now.isBefore(end)` | `!now.isBefore(end)` |
| Include `end` | `!now.isAfter(end)` | `now.isAfter(end)` |

A typical mistake is choosing an exclusive endpoint but using `now.isAfter(end)` to check for expiration: at the exact end boundary, it is still treated as not expired.

To check an entire half-open interval, write `!now.isBefore(start) && now.isBefore(end)`. Do not use the `==` operator to compare values of temporal objects. [Instant: comparing instants](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

## 4. "Through the end of the day" is a separate contract

If access is valid **through the end of March 30 in Berlin time**, the inputs are a calendar date and a zone. This can be converted into an exclusive end boundary at the start of March 31 in that zone.

```java
// Inside a method, with validThrough and zone already defined.
Instant endExclusive = validThrough.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
```

Do not pick `23:59:59` or `23:59:59.999` as the "last second": that meaning depends on precision and easily misses smaller fractional parts. Do not add 24 hours to the start of the day to find the end of the day in zones with daylight saving time transitions.

`atStartOfDay(zone)` uses the earliest valid instant of the day according to the zone rules. A local day can be 23 or 25 hours long; the next calendar day itself is the boundary you want. If the input date is at the `LocalDate.MAX` boundary, finding the next day requires a separate policy or rejection for exceeding the domain. [LocalDate.atStartOfDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId))

The rule "the last day is included" does not mean you must use an inclusive end timestamp. You can keep the inclusive end date in the business model and convert it to an exclusive start-of-next-day instant at the enforcement boundary.

## 5. A program to test the exact boundary points

Save as `ExpiryBoundaryDemo.java`. `TimeWindow` below intentionally accepts only non-empty intervals with an inclusive start and an exclusive end.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class ExpiryBoundaryDemo {
    record TimeWindow(Instant startInclusive, Instant endExclusive) {
        TimeWindow {
            Objects.requireNonNull(startInclusive, "startInclusive");
            Objects.requireNonNull(endExclusive, "endExclusive");
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException("Window must be non-empty");
            }
        }

        boolean contains(Instant value) {
            return !value.isBefore(startInclusive) && value.isBefore(endExclusive);
        }
    }

    static boolean expiredExclusive(Instant now, Instant end) {
        return !now.isBefore(end);
    }

    static boolean expiredInclusive(Instant now, Instant end) {
        return now.isAfter(end);
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2025-03-30T10:00:00Z");
        Instant end = Instant.parse("2025-03-30T10:15:00Z");
        TimeWindow window = new TimeWindow(start, end);

        System.out.println("beforeStart=" + window.contains(start.minusNanos(1)));
        System.out.println("atStart=" + window.contains(start));
        System.out.println("beforeEnd=" + window.contains(end.minusNanos(1)));
        System.out.println("atEnd=" + window.contains(end));
        System.out.println("afterEnd=" + window.contains(end.plusNanos(1)));
        System.out.println("exclusiveExpiredAtEnd=" + expiredExclusive(end, end));
        System.out.println("inclusiveExpiredAtEnd=" + expiredInclusive(end, end));

        Clock fixed = Clock.fixed(end, ZoneOffset.UTC);
        Instant evaluationTime = Instant.now(fixed);
        System.out.println("fixedClockExpired="
                + expiredExclusive(evaluationTime, end));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDate validThrough = LocalDate.of(2025, 3, 30);
        Instant dayStart = validThrough.atStartOfDay(berlin).toInstant();
        Instant dayEnd = validThrough.plusDays(1).atStartOfDay(berlin).toInstant();
        System.out.println("dayEndExclusive=" + dayEnd);
        System.out.println("dayLengthHours="
                + Duration.between(dayStart, dayEnd).toHours());
    }
}
```

Run with JDK 17 or later:

```shell
javac --release 17 ExpiryBoundaryDemo.java
java ExpiryBoundaryDemo
```

Stdout with IANA Berlin rules for 2025:

```text
beforeStart=false
atStart=true
beforeEnd=true
atEnd=false
afterEnd=false
exclusiveExpiredAtEnd=true
inclusiveExpiredAtEnd=false
fixedClockExpired=true
dayEndExclusive=2025-03-30T22:00:00Z
dayLengthHours=23
```

`minusNanos(1)` and `plusNanos(1)` only create test data before and after the boundary. They are not a way to fix a contract by shifting the expiration time by a tiny amount. March 30 in the example is 23 hours long, yet the start of the next day is still clearly determined.

`Clock.fixed` helps test exact equality without depending on machine speed or execution time. In business code, pass a `Clock` or an evaluation `Instant` into functions instead of calling the system clock directly across multiple branches. [Clock.fixed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId))

## 6. Storage precision must not silently change the convention

A system might process nanoseconds in Java, store only microseconds in the DB, and display down to seconds in the UI. If the end boundary is rounded on write or read, the actual comparison point may differ from the one originally created.

Define the preserved precision, the rounding/truncation rule, and the canonical representation used for decisions. Test after data passes through the API/DB, not only while values are still in memory.

Do not convert an inclusive endpoint into an exclusive one by always adding 1 nanosecond if the infrastructure does not preserve nanoseconds; likewise, do not subtract 1 millisecond to simulate "end of day." Compare directly according to the contract or use a natural calendar boundary such as the start of the next day.

Displaying `10:15:00` can hide the true fractional part of the instant; when tracing boundary bugs, you need to know the exact value and unit. Remaining duration displayed in whole minutes is also not the sole condition for deciding expiration.

## 7. Use the same contract across Java, queries, and APIs

A query for a half-open interval can be expressed as:

```sql
WHERE valid_from <= :evaluation_time
  AND :evaluation_time < expires_at
```

This is an illustrative expression using named parameters; exact binding depends on the library/DB. If the contract uses an inclusive endpoint, the final comparison must be `<=` with the same meaning. Do not let Java use `<` while the query uses `<=`.

For example, PostgreSQL defines `BETWEEN` as inclusive on both ends; do not directly replace a half-open interval condition with that expression. [PostgreSQL: BETWEEN](https://www.postgresql.org/docs/current/functions-comparison.html)

Names such as `endExclusive`, `validThroughDate`, and `expiresAt` paired with boundary documentation help communicate intent. A generic name like `endTime` without a contract leaves the exact endpoint behavior as a question for every developer.

If an unbounded expiration is allowed, the model must express that explicitly; do not arbitrarily use `null`, epoch, or `Instant.MAX` as stand-ins that different components interpret differently.

## 8. Choose a single evaluation time for the entire decision

Within a single processing pass, capture the evaluation time once and use it consistently. If you call `now()` when checking the start condition and call it again for the end condition, the two timestamps could fall on opposite sides of a boundary.

You also need to decide whether the decision is based on request arrival time, operation start time, or the time the DB evaluates it. A request that arrives before the deadline but is processed after the deadline has an outcome determined by that policy; changing `>` to `>=` does not solve the whole question.

For an update operation that needs to enforce the expiration condition at the DB level, you can include the time condition alongside the write operation within the transaction contract, then check the update result. Pre-checking in the application does not guarantee the condition stays true throughout subsequent processing.

## 9. Practice exercises

1. Write a truth table of results before, at, and after the endpoint for both contracts.
2. Split the interval `[09:00, 11:00)` into two adjacent intervals at 10:00; which interval does 10:00 belong to?
3. Convert the requirement "usable through the end of December 31 in Vietnam" into an exclusive end boundary.
4. Check the case where an instant stored in the DB is truncated from nanoseconds to milliseconds.

Check your answers: (1) they differ only at the point of equality; (2) it belongs to `[10:00, 11:00)`; (3) start of January 1 of the following year in `Asia/Ho_Chi_Minh`; (4) compare against the agreed representation and verify after a write/read round-trip.