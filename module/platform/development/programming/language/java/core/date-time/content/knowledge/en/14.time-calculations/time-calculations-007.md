# Precision Truncation vs. Time Rounding in Java

When a timestamp needs to be stored at a lower resolution than its current value, such as from nanoseconds to milliseconds, there are two common approaches: **truncating the part smaller than the target resolution (truncation)** and **rounding to the nearest value (rounding)**. These two approaches are not the same. If a database only stores milliseconds while the application sends nanoseconds, choosing truncation versus rounding can shift the point in time by nearly a millisecond; for pre-epoch data, a mistake in the rule can also easily cause a one-sided error.

In Java, `Instant.truncatedTo(ChronoUnit.MILLIS)` drops the part smaller than a millisecond; it **does not round automatically**. The `java.time` API does not provide a general-purpose `Instant.roundToMillis()` method, so the application needs to choose and implement a rounding policy that fits its business requirements.

## 1. What Are Resolution, Precision, and Accuracy?

- **Resolution:** the smallest step that a format or storage system can represent, such as 1 second, 1 millisecond, or 1 microsecond.
- **Precision:** the number of fractional digits of a second that are stored or measured. `Instant` represents values down to nanoseconds.
- **Accuracy:** how close the value measured by the clock source is to the true point in time. A timestamp with 9 nanosecond digits does not prove that the clock is actually accurate to the nanosecond.

For example, `2026-10-24T10:15:30.123789456Z` has nanosecond representation resolution. If the target system only stores milliseconds, we must choose a policy to normalize it to a `0.001`-second step.

| Input | Target resolution | Truncation | Round to nearest |
| --- | --- | --- | --- |
| `10:15:30.123100Z` | 1 ms | `10:15:30.123Z` | `10:15:30.123Z` |
| `10:15:30.123500Z` | 1 ms | `10:15:30.123Z` | `10:15:30.124Z` under a forward tie-breaking policy |
| `10:15:30.123789Z` | 1 ms | `10:15:30.123Z` | `10:15:30.124Z` |
| `10:15:30.999900Z` | 1 ms | `10:15:30.999Z` | `10:15:31.000Z` |

Rounding can **push a timestamp into the next second, day, or month**, because the rounding step moves to the target boundary. Truncation keeps the whole part of the target unit according to the timeline used by the API type, though it is also important to understand how negative instants are handled.

## 2. Truncating with `truncatedTo()`

`Instant.truncatedTo(TemporalUnit)` returns a new instant truncated to the chosen unit. Commonly used units include `ChronoUnit.SECONDS`, `MILLIS`, `MICROS`, `MINUTES`, or `HOURS`; the unit must be supported by `Instant`.

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant value = Instant.parse("2026-10-24T10:15:30.123789456Z");

System.out.println(value.truncatedTo(ChronoUnit.SECONDS));
// 2026-10-24T10:15:30Z

System.out.println(value.truncatedTo(ChronoUnit.MILLIS));
// 2026-10-24T10:15:30.123Z

System.out.println(value.truncatedTo(ChronoUnit.MICROS));
// 2026-10-24T10:15:30.123789Z

System.out.println(value.truncatedTo(ChronoUnit.MINUTES));
// 2026-10-24T10:15:00Z
```

`truncatedTo` **does not mutate** the original object. Save the returned value if you want to use the reduced-resolution timestamp:

```java
Instant original = Instant.parse("2026-10-24T10:15:30.123789456Z");
original.truncatedTo(ChronoUnit.MILLIS); // Result is ignored
System.out.println(original);
// 2026-10-24T10:15:30.123789456Z
```

If you need to keep milliseconds in a new variable, use `Instant millis = original.truncatedTo(ChronoUnit.MILLIS);`.

### Truncation in `LocalTime` and Local Types

`LocalTime` and `LocalDateTime` also support `truncatedTo`:

```java
LocalTime time = LocalTime.of(10, 15, 30, 987_654_321);
System.out.println(time.truncatedTo(ChronoUnit.SECONDS));
// 10:15:30

LocalDateTime local = LocalDateTime.of(2026, 10, 24, 10, 15, 30, 987_654_321);
System.out.println(local.truncatedTo(ChronoUnit.MILLIS));
// 2026-10-24T10:15:30.987
```

Truncating `LocalDateTime` only adjusts the local date-time fields; it does not add an offset or time zone. If you later attach it to a zone with DST, you must resolve the zone rules separately.

`ZonedDateTime.truncatedTo` also works on supported units, but when rounding or truncating calendar units around DST, you must define the intended semantics clearly. For example, `DAYS` on a zone is a local day, which may be 23 or 25 hours long in instant time. For absolute timestamps that need to be truncated to a multiple of milliseconds or seconds, operating directly on `Instant` usually expresses intent more clearly.

## 3. Truncation Is Not Dividing a Number and Dropping Digits

A common misconception is thinking `truncatedTo` behaves like a mathematical "drop the trailing digits" function without considering the timeline. For `Instant`, the epoch seconds and nanosecond part are represented in normalized form: `epochSecond` is the whole seconds relative to the epoch, and `nano` is in the range 0–999,999,999.

Consider points near the epoch:

| Instant | `getEpochSecond()` | `getNano()` | Truncated to milliseconds |
| --- | ---: | ---: | --- |
| `1970-01-01T00:00:00.0009Z` | 0 | 900000 | `1970-01-01T00:00:00Z` |
| `1969-12-31T23:59:59.9999Z` | -1 | 999900000 | `1969-12-31T23:59:59.999Z` |
| `1969-12-31T23:59:59.5004Z` | -1 | 500400000 | `1969-12-31T23:59:59.500Z` |
| `1969-12-31T23:59:59.9990Z` | -1 | 999000000 | `1969-12-31T23:59:59.999Z` |

For a negative instant, `getEpochSecond()` can be `-1` while `getNano()` is close to one billion. For example, `1969-12-31T23:59:59.9999Z` is **0.1 milliseconds before the epoch**. Truncating to millisecond resolution along timeline boundaries yields `...59.999Z`, which is -1 ms relative to the epoch. Do not divide `getNano()` independently and forget the negative seconds part; also do not use `Math.abs` to process timestamps.

## 4. What Is Rounding and Why Do You Need a Policy?

Rounding maps a value to the nearest grid point of the target resolution. However, when a value lies **exactly halfway between two points**, there are multiple valid rules:

| Rule | On an exact midpoint | Numerical example |
| --- | --- | --- |
| Half-up on the timeline | Choose the later point (larger instant) | 1.5 → 2; -1.5 on timeline → -1 |
| Half-away-from-zero | Move away from 0 | 1.5 → 2; -1.5 → -2 |
| Half-even (banker's rounding) | Choose the point with an even last digit | 2.5 → 2; 3.5 → 4 |
| Toward zero | Move toward 0 | 1.9 → 1; -1.9 → -1 |
| Floor | Choose the multiple no greater than input | -1.2 → -2 |
| Ceiling | Choose the multiple no less than input | -1.2 → -1 |

For timestamps, "up" should be defined on the **timeline**, meaning a later instant, rather than the positive/negative sign of a number. Half-up on the timeline and half-away-from-zero differ for negative times: half-up on the timeline moves an exact midpoint toward the later point in time; half-away-from-zero moves negative times farther away from the epoch.

Therefore, before writing a rounding helper, settle on:

- Target unit: seconds, milliseconds, or microseconds?
- Midpoint: move toward the later instant, the earlier instant, toward zero, or to even?
- Do pre-epoch timestamps need to be handled?
- Can overflow occur at range boundaries?
- Does normalized data need to match across Java, the database, and other languages?

## 5. Rounding `Instant` to Milliseconds: Half-Up on the Timeline

A simple way to round to milliseconds and choose the **later** point on an exact half-millisecond tie is to add half a step (500,000 nanoseconds), then truncate to milliseconds:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

static Instant roundToMillisHalfUpTimeline(Instant value) {
    return value.plusNanos(500_000L)
            .truncatedTo(ChronoUnit.MILLIS);
}
```

This function needs to be placed inside a Java class; the code fence is a method snippet, not a standalone program. It applies the "half a step or more chooses the next point" rule on the **timeline**, including negative timestamps. A few examples:

| Input | Truncated with `truncatedTo(MILLIS)` | Half-up on the timeline |
| --- | --- | --- |
| `1970-01-01T00:00:00.0004Z` | `...00.000Z` | `...00.000Z` |
| `1970-01-01T00:00:00.0005Z` | `...00.000Z` | `...00.001Z` |
| `1970-01-01T00:00:00.0006Z` | `...00.000Z` | `...00.001Z` |
| `1969-12-31T23:59:59.9994Z` | `...59.999Z` | `...59.999Z` |
| `1969-12-31T23:59:59.9995Z` | `...59.999Z` | `1970-01-01T00:00:00Z` |
| `1969-12-31T23:59:59.9996Z` | `...59.999Z` | `1970-01-01T00:00:00Z` |

Adding 500,000 nanoseconds to a negative timestamp also works because `Instant` normalizes seconds and nanoseconds along the timeline. **This is half-up toward the later instant**, not half-away-from-zero for negative numbers. At the same time, the addition can throw `DateTimeException` if the input is already too close to `Instant.MAX`; the system needs a clear rule for boundary cases.

### Why Not Use `Math.round(value.toEpochMilli())`?

`toEpochMilli()` has already dropped the sub-millisecond part before `Math.round` is called. The information needed for rounding is already lost, so `Math.round` cannot recover it. For example, two instants `.1231Z` and `.1239Z` both return the same epoch millisecond after `toEpochMilli()`, even though a rounding policy would move the second value to the next millisecond.

Round on the original `Instant` before converting to a lower-resolution storage unit; do not convert to a `long` of milliseconds first and expect to round the original nanoseconds.

## 6. Rounding to Microseconds and Seconds

The idea of adding half a step and then truncating can be applied to other fixed units supported by `Instant.truncatedTo`:

```java
static Instant roundToMicrosHalfUpTimeline(Instant value) {
    return value.plusNanos(500L)
            .truncatedTo(ChronoUnit.MICROS);
}

static Instant roundToSecondsHalfUpTimeline(Instant value) {
    return value.plusNanos(500_000_000L)
            .truncatedTo(ChronoUnit.SECONDS);
}
```

- A microsecond has a 1,000-nanosecond step, so half a step is 500 ns.
- A second has a half-step of 500,000,000 ns.
- A millisecond has a 1,000,000-ns step, so half a step is 500,000 ns.

The functions above use the same **half-up on the instant timeline** policy, where exact ties go to the later instant. Do not apply this formula mechanically to all calendar units such as months, years, or days in `ZonedDateTime`. A local day across DST is not necessarily 86,400 seconds; "rounding to a calendar day" requires its own calendar policy.

In addition, `plusNanos` has range limits like any operation on `Instant`. If handling extreme instants, define how errors are reported or use a boundary-checked algorithm.

## 7. Rounding `long` Epoch Milliseconds: Be Careful with Negative Numbers

Some systems store timestamps as a `long` number of milliseconds since the epoch. If you are already in **millisecond units** and only need to round that integer to a multiple of 10 ms or 1,000 ms, you must choose a clear arithmetic rule. Do not mix nanosecond and millisecond units.

For example, if the input is `epochMillis` and you want to round to 100 ms using timeline-forward half-up, you can split the quotient and remainder using `floorDiv`/`floorMod` with a positive step so that negative numbers are handled properly along the timeline:

```java
static long roundMillisTo100msHalfUpTimeline(long epochMillis) {
    long step = 100L;
    long lower = Math.floorDiv(epochMillis, step) * step;
    long remainder = Math.floorMod(epochMillis, step);
    return remainder < step / 2 ? lower : lower + step;
}
```

This is a helper for **100-millisecond multiples**. At the exact midpoint, it chooses the later multiple. However, `lower + step` can overflow when the input is near `Long.MAX_VALUE`; production code needs boundary checks using `Math.addExact` or a specific overflow policy.

For example, `epochMillis = -1` lies between `-100` and `0`, closer to 0, so it returns 0; `epochMillis = -50` is at the exact midpoint, so it also returns 0 under the rule that ties go toward the later timeline point. A calculation like `(epochMillis + step / 2) / step * step` can be wrong because Java integer division truncates toward 0 and adding/subtracting near boundaries can overflow.

If the data starts as an `Instant` with nanosecond resolution, prefer rounding directly on the original `Instant`. The integer helper above is only appropriate when you know the input is already epoch milliseconds and the output rule is also in milliseconds.

## 8. Is Truncation the Same as `toEpochMilli()`?

`Instant.toEpochMilli()` returns a `long` of milliseconds from the epoch and **drops precision smaller than a millisecond**. For standard instants, this behavior aligns with the millisecond timeline and handles negative values; do not replace it with `epochSecond * 1000 + nano / 1_000_000` without proving how negative numbers and overflow are handled.

```java
Instant precise = Instant.parse("1969-12-31T23:59:59.999999999Z");
System.out.println(precise.truncatedTo(ChronoUnit.MILLIS));
// 1969-12-31T23:59:59.999Z
System.out.println(precise.toEpochMilli());
// -1
```

`toEpochMilli()` does not return a timestamp as a double or float; it returns a `long` integer. Instants with different nanoseconds but the same millisecond can produce the same `toEpochMilli()` result, so **this is a lossy conversion**.

If the system needs to distinguish events before and after a millisecond boundary, keep `Instant` or a seconds/nanos pair. If the target schema intentionally stores milliseconds, losing the nanosecond part should be treated as a deliberate policy decision rather than an accidental side effect.

## 9. Decide Where to Apply Precision Reduction

Reducing resolution at different layers can produce inconsistent results:

- **Formatting for display:** if you only need readable text, you can display 3 millisecond digits without altering the internal instant. Do not round the core value just because the UI displays fewer digits.
- **Database storage:** check the timestamp type and resolution of the column/driver. Some drivers or databases truncate or round automatically; test by writing and reading back boundary values.
- **API communication:** specify how many fractional digits an ISO instant has or whether numeric epoch values are in ms/µs/ns. Both sides must agree on the tie-breaking policy if rounding.
- **Comparison/deduplication:** rounding or truncating before comparing can cause two distinct events to share the same timestamp. If uniqueness has business meaning, use a separate event ID instead of relying solely on the timestamp.
- **Duration measurement:** wall-clock timestamp precision is not the same as measurement accuracy. For elapsed time within a process, consider `System.nanoTime()` instead of rounding `Instant.now()`.

**In particular:** do not round only on the read side while truncating on the write side if comparison results or data signatures must match. Choose one canonicalization policy at the system boundary, document it clearly, and apply it consistently.

## 10. Standalone Java 17+ Program

Create the file **`PrecisionReductionDemo.java`**:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class PrecisionReductionDemo {
    static Instant truncateMillis(Instant value) {
        return value.truncatedTo(ChronoUnit.MILLIS);
    }

    static Instant roundMillisHalfUpTimeline(Instant value) {
        return value.plusNanos(500_000L)
                .truncatedTo(ChronoUnit.MILLIS);
    }

    static Instant roundMicrosHalfUpTimeline(Instant value) {
        return value.plusNanos(500L)
                .truncatedTo(ChronoUnit.MICROS);
    }

    public static void main(String[] args) {
        Instant[] samples = {
                Instant.parse("2026-10-24T10:15:30.123100Z"),
                Instant.parse("2026-10-24T10:15:30.123500Z"),
                Instant.parse("2026-10-24T10:15:30.123789Z"),
                Instant.parse("1969-12-31T23:59:59.999400Z"),
                Instant.parse("1969-12-31T23:59:59.999500Z"),
                Instant.parse("1969-12-31T23:59:59.999600Z")
        };

        for (Instant input : samples) {
            System.out.println("input = " + input);
            System.out.println("  trunc ms = " + truncateMillis(input));
            System.out.println("  round ms = "
                    + roundMillisHalfUpTimeline(input));
        }

        Instant value = Instant.parse("2026-10-24T10:15:30.123789456Z");
        System.out.println("trunc micros = "
                + value.truncatedTo(ChronoUnit.MICROS));
        System.out.println("round micros = "
                + roundMicrosHalfUpTimeline(value));
        System.out.println("original = " + value);
    }
}
```

Compile and run:

```bash
javac PrecisionReductionDemo.java
java PrecisionReductionDemo
```

Expected output:

```text
input = 2026-10-24T10:15:30.123100Z
  trunc ms = 2026-10-24T10:15:30.123Z
  round ms = 2026-10-24T10:15:30.123Z
input = 2026-10-24T10:15:30.123500Z
  trunc ms = 2026-10-24T10:15:30.123Z
  round ms = 2026-10-24T10:15:30.124Z
input = 2026-10-24T10:15:30.123789Z
  trunc ms = 2026-10-24T10:15:30.123Z
  round ms = 2026-10-24T10:15:30.124Z
input = 2026-10-24T10:15:30.999400Z
  trunc ms = 2026-10-24T10:15:30.999Z
  round ms = 2026-10-24T10:15:30.999Z
input = 2026-10-24T10:15:30.999500Z
  trunc ms = 2026-10-24T10:15:30.999Z
  round ms = 2026-10-24T10:15:31Z
input = 2026-10-24T10:15:30.999600Z
  trunc ms = 2026-10-24T10:15:30.999Z
  round ms = 2026-10-24T10:15:31Z
trunc micros = 2026-10-24T10:15:30.123789Z
round micros = 2026-10-24T10:15:30.123789Z
original = 2026-10-24T10:15:30.123789456Z
```

The last lines show that truncating to microseconds and rounding to microseconds can match when the remainder is less than half a step; for other values, the two results will differ. `original` retains its nanoseconds because `Instant` is immutable.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Calling `truncatedTo(MILLIS)` and expecting it to round | Always drops the sub-millisecond part | Use an explicit rounding rule if the nearest point is needed |
| Calling `toEpochMilli()` before rounding | Nanoseconds are already lost and cannot be recovered | Round the original `Instant` first |
| Using integer division on negative timestamps without checking the rule | Can be off by one step near the epoch | Use the `Instant` API or `floorDiv`/`floorMod` with a defined unit |
| Rounding a nanosecond value already converted to `long` milliseconds | Sub-millisecond information has already disappeared | Keep source resolution until the policy is applied |
| Assuming all systems use the same tie-breaking rule | Java, databases, languages, and configurations may differ | Specify half-up, half-even, floor, truncation, etc. in the contract |
| Using `double` to store epoch nanoseconds | Loss of precision for large integers | Use an appropriate integer type, a seconds+nanos pair, or a string |
| Rounding at every intermediate calculation | Accumulated error across steps | Keep exact values and only reduce resolution at the chosen boundary |
| Comparing only rounded timestamps for deduplication | Two close events can collapse to the same point | Use an event ID and a dedicated deduplication rule |
| Applying half-step addition without checking for overflow | Extreme values can throw an exception | Validate the range and define boundary handling |
| Confusing nanosecond resolution with measurement accuracy | Trusting a timestamp to be more accurate than the true source | Separate type precision from clock accuracy |

## 12. Policy Selection Checklist

1. **Identify the target unit:** 1 s, 1 ms, 1 µs, or another unit.
2. **Choose the transformation:** truncation/floor or rounding to nearest.
3. **Lock down midpoint handling:** half-up on the timeline, half-even, or half-away-from-zero.
4. **Test negative timestamps:** add pre-epoch tests, including just below, exactly at, and just above half-steps.
5. **Check carry-over:** rounding can roll over into a new second or day.
6. **Check limits:** `Instant.MIN/MAX`, epoch `long` overflow, and database limits.
7. **Define where normalization happens:** API, application, driver, or database; avoid multiple layers applying different policies.
8. **Keep original data when needed for auditing:** if the discarded resolution is meaningful, store the original value alongside the normalized value or policy metadata.

### Self-Check Questions

**1.** What does `Instant.parse("2026-10-24T10:15:30.123789Z").truncatedTo(MILLIS)` return?  
→ `2026-10-24T10:15:30.123Z`, because it drops the nanosecond part smaller than a millisecond.

**2.** Using the half-up-on-the-timeline helper, which millisecond does `.123500Z` round to?  
→ `.124Z`, because it is an exact half-millisecond and the policy chooses the later instant.

**3.** Why doesn't `Math.round(instant.toEpochMilli())` round the original nanoseconds?  
→ `toEpochMilli()` has already dropped the sub-millisecond part before `Math.round` is called.

**4.** Is a pre-epoch `Instant` with a negative `getEpochSecond()` and a positive `getNano()` valid?  
→ Yes; nanoseconds are normalized from 0 to 999,999,999.

**5.** Should adding half a step and truncating be applied directly for "rounding to a local day" on any `ZonedDateTime`?  
→ No; a local day can be 23 or 25 hours around DST. Rounding calendar days requires separate calendar rules.

**6.** If a DB column only stores milliseconds, can the application drop nanoseconds by default without an agreement?  
→ You should define and test the normalization policy at the storage/read boundary, because drivers or DBs may truncate or round differently.

### Official API Documentation

- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): seconds+nanos structure, `truncatedTo`, `toEpochMilli`, `plusNanos`.
- [Java SE 17 — `ChronoUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): millisecond, microsecond, second, and supported time units.
- [Java SE 17 — `LocalTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html): truncating local time fields.
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): local operations and zone/DST rules.

**Key takeaway:** `truncatedTo` drops the part smaller than the unit, whereas rounding chooses the nearest multiple according to a specific policy. Keep the full `Instant` until you know what resolution the storage target requires; define the midpoint policy, test negative timestamps, and align the rules across all systems.
