# Converting LocalDateTime to Epoch Requires the Appropriate UTC Offset

When converting a date-time to an **epoch** (the number of seconds or milliseconds since `1970-01-01T00:00:00Z`), a common mistake is passing a `LocalDateTime` into a conversion **without knowing which UTC offset it belongs to**. `LocalDateTime` only has year, month, day, hour, minute, second, and nanosecond fields. It **contains no time zone and no UTC offset**. Therefore, the value `2024-08-15T09:30` alone does not identify an absolute point in time.

For example, with the same local time `2024-08-15 09:30`:

- With offset `+07:00`, it corresponds to `2024-08-15T02:30:00Z`.
- With offset `+00:00`, it corresponds to `2024-08-15T09:30:00Z`.
- With offset `-04:00`, it corresponds to `2024-08-15T13:30:00Z`.

These three instants differ by **7 hours or 11 hours** even though all `LocalDateTime` fields are identical. To convert to epoch accurately, you must determine the **actual UTC offset that applies to that date-time**, or provide a **ZoneId** to look up zone rules and handle nonexistent or repeated hours.

## 1. Distinguishing LocalDateTime, ZoneOffset, ZoneId, and Instant

| Type | What does it contain? | Can it identify an Instant? | Role |
|---|---|---|---|
| `LocalDateTime` | Local date and time, without offset/zone. | **No**, if standing alone. | Expresses "09:30 on August 15" on the calendar. |
| `ZoneOffset` | Fixed offset from UTC, e.g., `+07:00` or `-04:00`. | When combined with `LocalDateTime`, **yes**. | Maps local time onto the timeline using a known offset. |
| `ZoneId` | Region identity and offset rules that can change historically, e.g., `Asia/Ho_Chi_Minh`, `America/New_York`. | Can be resolved using zone rules, but **gap/overlap** must be handled. | Interprets local time according to time zone rules on a specific date. |
| `OffsetDateTime` | `LocalDateTime` plus a `ZoneOffset`. | **Yes**. | Carries local time and a definite offset at an event. |
| `ZonedDateTime` | Date-time plus `ZoneId` and a resolved offset. | **Yes**. | Calendar and instant bound to zone rules. |
| `Instant` | Absolute point in time on the Java timeline. | It is itself an instant. | Storing timestamps, inter-system communication, measuring intervals between events. |

An offset like `+07:00` is the **clock offset at a point in time**, not the name of a region. For example, `Asia/Ho_Chi_Minh` currently uses `+07:00`, but a zone also contains historical information and rules that can change; you should not replace `ZoneId` with a fixed offset in future scheduling problems.

Intuitive formula:

~~~text
UTC instant = local date/time - UTC offset

09:30 +07:00 -> 02:30 UTC
09:30 -04:00 -> 13:30 UTC
~~~

If local time is 7 hours "ahead" of UTC (`+07:00`), then UTC must be **7 hours behind** local time, not plus 7 hours. The offset sign is very easy to get backwards.

## 2. Epoch second, epoch milli, and units

The **Unix epoch** is the reference point `1970-01-01T00:00:00Z`. In common Java time APIs:

- `Instant.getEpochSecond()` and `LocalDateTime.toEpochSecond(ZoneOffset)`: number of **seconds** since the epoch, of type `long`.
- `Instant.toEpochMilli()`: number of **milliseconds** since the epoch, of type `long`.
- Sub-second fractions are kept in `Instant.getNano()` or the nano field of the corresponding object.

Do not confuse `epochSecond` and `epochMilli`: the two values typically differ by a factor of **1,000**. For example, `1723689000` seconds corresponds to `1723689000000` milliseconds, representing the same instant.

**Times before the epoch** have negative values. For `1969-12-31T23:59:59.500Z`, `getEpochSecond()` is `-1` and `toEpochMilli()` is `-500`. This is consistent with whole seconds relative to the epoch and a fractional nano part; it does not mean "a negative second cannot have a fractional part."

**Not nanoseconds since the epoch:** `System.nanoTime()` is unrelated to the Unix epoch, has an arbitrary origin, and is used to measure elapsed duration. Do not convert it directly into an `Instant`.

## 3. When the exact UTC offset is known

If the input `LocalDateTime` **comes with a valid, verified UTC offset**, there are two equivalent approaches:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 8, 15, 9, 30);
ZoneOffset offset = ZoneOffset.ofHours(7);

long seconds = local.toEpochSecond(offset);
Instant instant = local.atOffset(offset).toInstant();
long millis = instant.toEpochMilli();
~~~

This is an illustrative snippet; to run it, import the `java.time` classes and place it inside a method/class.

- `local.toEpochSecond(offset)` returns epoch seconds and requires the **offset supplied by the caller**.
- `local.atOffset(offset)` creates an `OffsetDateTime`; `toInstant()` gives the absolute instant, from which you can retrieve seconds/milliseconds and the nano part.
- You do not need to write hour-subtraction formulas manually, avoiding sign errors and date rollover bugs.

**Important:** `toEpochSecond(offset)` **does not automatically look up a ZoneId to validate the offset**. If you mistakenly pass `+07:00` for a time that actually belongs to `-04:00`, Java will still compute an arithmetically valid number, but that number represents the **wrong point in time**.

### Complete example with deterministic output

File `FixedOffsetEpochDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class FixedOffsetEpochDemo {
    public static void main(String[] args) {
        LocalDateTime local = LocalDateTime.of(2024, 8, 15, 9, 30);
        ZoneOffset offset = ZoneOffset.ofHours(7);

        OffsetDateTime withOffset = local.atOffset(offset);
        Instant instant = withOffset.toInstant();

        System.out.println("Local: " + local);
        System.out.println("Offset: " + offset);
        System.out.println("OffsetDateTime: " + withOffset);
        System.out.println("UTC: " + instant);
        System.out.println("Seconds: " + local.toEpochSecond(offset));
        System.out.println("Millis: " + instant.toEpochMilli());
        System.out.println("Reconstructed: "
                + LocalDateTime.ofInstant(instant, offset));
    }
}
~~~

Run on JDK 17+:

~~~bash
javac FixedOffsetEpochDemo.java
java FixedOffsetEpochDemo
~~~

Output:

~~~text
Local: 2024-08-15T09:30
Offset: +07:00
OffsetDateTime: 2024-08-15T09:30+07:00
UTC: 2024-08-15T02:30:00Z
Seconds: 1723689000
Millis: 1723689000000
Reconstructed: 2024-08-15T09:30
~~~

With the same local time numbers, if you intentionally change the offset to `UTC` (`ZoneOffset.UTC`), the epoch value will correspond to `2024-08-15T09:30Z`, which is exactly 7 hours later than the `+07:00` result. Having data in Vietnam time **does not allow** defaulting it to UTC.

## 4. If you know the location/time zone, use ZoneId

In real-world data, users often provide a **location or zone name**, such as "09:00 New York time" or "18:30 Vietnam time". In that case, the offset must be determined **for that specific date and time in the zone**, because some zones switch DST or change time zone policies.

Example:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime winter = LocalDateTime.of(2024, 1, 15, 9, 0);
LocalDateTime summer = LocalDateTime.of(2024, 7, 15, 9, 0);

ZonedDateTime winterZoned = winter.atZone(zone);
ZonedDateTime summerZoned = summer.atZone(zone);
~~~

This is an illustrative snippet; you need to import `java.time` and place it in a program. In New York in 2024, winter `09:00` uses `-05:00`, while summer `09:00` uses `-04:00`. You cannot take **today's** offset and apply it to all past or future dates.

To convert:

~~~text
LocalDateTime + ZoneId
        |
        v
Apply ZoneRules at local date/time
        |
        v
ZonedDateTime (offset resolved; requires gap/overlap policy)
        |
        v
Instant -> epoch second / epoch milli
~~~

Typical API steps:

~~~java
ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
long epochSecond = instant.getEpochSecond();
long epochMilli = instant.toEpochMilli();
~~~

This is also an illustrative snippet, where `local` and `zone` must already be declared. This approach is usually suitable when the time is interpreted according to a local calendar at a location, but **`atZone` has a default policy when encountering DST**. For scheduling or sensitive business data, you must evaluate that policy before converting.

## 5. DST can cause a LocalDateTime to have no Instant or two Instants

In a zone with *daylight saving time* (DST), clocks can spring forward or fall back, leading to two cases:

**Gap — the local time does not exist.** In `America/New_York` on 2024-03-10, the clock jumps from 01:59:59 (`-05:00`) to 03:00:00 (`-04:00`). The time `2024-03-10T02:30` does not exist under this zone's rules. If you use `local.atZone(zone)`, Java by default **pushes 02:30 forward to 03:30** by the length of the gap, yielding `2024-03-10T03:30-04:00`. This adjustment may be inappropriate if the system needs to reject nonexistent times.

**Overlap — one local time has two instants.** On 2024-11-03, New York clocks fall back from 01:59:59 (`-04:00`) to 01:00:00 (`-05:00`). Thus `2024-11-03T01:30` can be:

- `2024-11-03T01:30-04:00` = `2024-11-03T05:30:00Z`, epoch second `1730611800`.
- `2024-11-03T01:30-05:00` = `2024-11-03T06:30:00Z`, epoch second `1730615400`.

`LocalDateTime` alone does not tell you whether the user meant the first or second occurrence of 01:30. `atZone` defaults to preferring the pre-transition offset in this case (`-04:00`); you can call `withLaterOffsetAtOverlap()` to get the later occurrence.

### Example: checking valid offsets and choosing the earlier or later occurrence

File `DstEpochDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class DstEpochDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        System.out.println("Gap offsets: " + rules.getValidOffsets(gap));
        System.out.println("Gap default: " + gap.atZone(newYork));

        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));

        ZonedDateTime earlier = overlap.atZone(newYork);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Earlier: " + earlier);
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Earlier epoch: "
                + earlier.toEpochSecond());

        System.out.println("Later: " + later);
        System.out.println("Later instant: " + later.toInstant());
        System.out.println("Later epoch: "
                + later.toEpochSecond());

        ZoneOffset chosen = ZoneOffset.ofHours(-5);
        ZonedDateTime strict = ZonedDateTime.ofStrict(
                overlap, chosen, newYork);
        System.out.println("Strict instant: " + strict.toInstant());
    }
}
~~~

Compile/run commands:

~~~bash
javac DstEpochDemo.java
java DstEpochDemo
~~~

Stdout with 2024 New York rules:

~~~text
Gap offsets: []
Gap default: 2024-03-10T03:30-04:00[America/New_York]
Overlap offsets: [-04:00, -05:00]
Earlier: 2024-11-03T01:30-04:00[America/New_York]
Earlier instant: 2024-11-03T05:30:00Z
Earlier epoch: 1730611800
Later: 2024-11-03T01:30-05:00[America/New_York]
Later instant: 2024-11-03T06:30:00Z
Later epoch: 1730615400
Strict instant: 2024-11-03T06:30:00Z
~~~

Key details to understand:

- `rules.getValidOffsets(local)` returns **0 offsets** in a gap, **1 offset** during normal hours, and **2 offsets** in an overlap.
- `LocalDateTime.atZone(zone)` handles gap/overlap using Java's default rules; this is a **decision** that the application should actively inspect.
- `ZonedDateTime.ofStrict(local, offset, zone)` requires the chosen offset to actually be valid for the zone at that local time; otherwise it throws `DateTimeException`.
- `toEpochSecond()` on `ZonedDateTime` uses the offset resolved inside the object. Two values with the same `LocalDateTime` during an overlap have different epochs.

A user-facing scheduling API should reject or ask how to handle a gap/overlap, rather than arbitrarily picking an instant and hiding the ambiguity.

## 6. Having an offset is not enough if you do not know it is valid for the zone and date

For example, `2024-03-10T02:30` in New York is a **nonexistent** time. Even so:

~~~java
LocalDateTime impossible = LocalDateTime.of(2024, 3, 10, 2, 30);
long seconds = impossible.toEpochSecond(ZoneOffset.ofHours(-5));
~~~

This is an illustrative snippet, not a standalone program; you need to import `java.time` and place it in a method. These two statements **do not automatically throw a DST exception** because `toEpochSecond(ZoneOffset)` simply treats `-05:00` as the supplied offset and computes the absolute instant. The result is `1710055800` (i.e., `2024-03-10T07:30:00Z`), yet the local label `02:30 -05:00` **was not a valid civil time** in New York at that moment.

If the requirement is simply "date-time with fixed offset `-05:00`," the conversion is valid for that *offset*, because `ZoneOffset` does not apply DST rules. If the requirement is "calendar time in `America/New_York`," you must validate against `ZoneRules`, and you must not assume a given offset is valid just because the arithmetic succeeded.

The same applies to an overlap: if an API silently picks one offset instead of asking or applying a policy, it drops the intent of choosing the **first/second occurrence**. The result can be off by an entire hour for logs, scheduling, accounting, or reconciliation.

### Pattern for strictly resolving a local time in a zone

The program `StrictLocalTimeDemo.java` illustrates the three valid possibilities:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictLocalTimeDemo {
    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, ZoneOffset selectedOffset) {

        List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local time does not exist in zone");
        }
        if (valid.size() == 2 && selectedOffset == null) {
            throw new IllegalArgumentException(
                    "Ambiguous local time; choose offset");
        }

        ZoneOffset offset = selectedOffset != null
                ? selectedOffset
                : valid.get(0);

        if (!valid.contains(offset)) {
            throw new IllegalArgumentException(
                    "Offset is not valid for local time");
        }
        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        ZonedDateTime result = resolve(
                overlap, zone, ZoneOffset.ofHours(-5));
        System.out.println(result.toInstant());
        System.out.println(result.toEpochSecond());
    }
}
~~~

Run:

~~~bash
javac StrictLocalTimeDemo.java
java StrictLocalTimeDemo
~~~

Stdout:

~~~text
2024-11-03T06:30:00Z
1730615400
~~~

The `resolve` method forces the caller to choose an offset when the local time is ambiguous. During normal hours, it automatically selects the single valid offset; if the caller supplies an invalid offset, the method rejects it. This is just **one illustrative policy**; for a gap, a product might have a policy to shift an appointment to the next valid time, which must be clearly specified and tested.

## 7. Nanosecond details: epoch seconds do not preserve the fractional part

`LocalDateTime.toEpochSecond(offset)` only returns **whole seconds**. If `LocalDateTime` has a nanosecond component, storing only seconds loses the fractional part.

Example:

~~~java
LocalDateTime local = LocalDateTime.of(
        2024, 8, 15, 9, 30, 0, 123_456_789);
Instant instant = local.atOffset(ZoneOffset.ofHours(7)).toInstant();

long seconds = instant.getEpochSecond();
int nanos = instant.getNano();
long millis = instant.toEpochMilli();
~~~

This is an illustrative snippet; you need to import the time classes and place it in a class/method. The corresponding results:

- `seconds = 1723689000`.
- `nanos = 123456789`.
- `millis = 1723689000123`; the sub-millisecond portion is no longer preserved in that integer millisecond count.

When you need a **nanosecond-accurate** round-trip, store an `Instant`, an appropriate ISO-8601 string, or an epochSecond/nano pair. `Instant.ofEpochSecond(seconds, nanos)` reconstructs the instant from those two components.

**Caution before the epoch:** negative seconds and fractional parts must be handled consistently according to Java's convention. For instance, the instant `1969-12-31T23:59:59.500Z` is represented as `epochSecond = -1`, `nano = 500000000`; `toEpochMilli()` is `-500`. Do not naively compute `epochSecond = epochMillis / 1000` using Java integer division if you need to preserve accuracy for negative epochs that are not whole seconds.

**Overflow/range:** `Instant.toEpochMilli()` can throw `ArithmeticException` if the result exceeds the `long` range. Java time objects support a much wider range than most application timestamps. For real data, validate the range and storage type.

## 8. Reading back from epoch: you must choose a zone to get the right LocalDateTime

An epoch identifies **one instant**, but how it is displayed as a local date and time depends on the zone:

~~~java
Instant instant = Instant.ofEpochSecond(1723689000L);
LocalDateTime inVietnam =
        LocalDateTime.ofInstant(instant, ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDateTime inUtc =
        LocalDateTime.ofInstant(instant, ZoneOffset.UTC);
~~~

This is an illustrative snippet; you need to import `java.time`. `inVietnam` is `2024-08-15T09:30`, while `inUtc` is `2024-08-15T02:30`. Both representations refer to the **same instant**.

To round-trip original calendar data:

1. Clearly determine which zone/offset the initial `LocalDateTime` belongs to.
2. Convert it to `Instant` and store the timestamp.
3. If you later want to display it in the **original zone**, also store the `ZoneId` (and, if relevant, the offset chosen during an overlap or the conversion policy).
4. When displaying it again, use `instant.atZone(zone)` or `LocalDateTime.ofInstant(instant, zone)`.

**You cannot uniquely infer a ZoneId from an epoch or an offset**: many zones share the same offset at a given point in time. Likewise, if you only store `LocalDateTime`, you cannot uniquely reconstruct the instant without knowing the offset/zone and the applied rules.

## 9. Practical considerations for JSON, databases, and APIs

### 9.1. Separate two kinds of business data

**Events that have occurred:** for example, "when was the order created?" — prefer storing an `Instant` or a timestamp with explicit offset/UTC information. You can transmit an ISO-8601 string with `Z` or an offset, or an epoch with an **explicitly stated unit** (`epochSecond` / `epochMillis`). Never automatically treat a string without an offset as UTC.

**Civil schedules/appointments:** for example, "08:30 on August 15 Hanoi time" or "09:00 every Monday New York time" — store the local date/time together with the `ZoneId`, recurrence rules, and DST handling policy. For a confirmed appointment, you can also store the resolved execution `Instant` and the offset chosen during an overlap.

### 9.2. A string without an offset does not automatically become UTC

`2024-08-15T09:30:00` is a valid string for `LocalDateTime.parse(...)`, but it **lacks an offset**. In contrast, `2024-08-15T09:30:00+07:00` carries an offset; `2024-08-15T02:30:00Z` carries UTC and identifies an instant.

When designing a JSON request, avoid ambiguous field names like `timestamp` without clearly documenting the format, time zone, and unit. A sample payload for an appointment might be:

~~~json
{
  "localDateTime": "2024-08-15T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

When processing this, the server must interpret the pair using `ZoneRules` for the scheduled time and then produce an `Instant`. For zones with overlaps, an extra field may be needed to select the offset or confirm with the user.

A payload for an event with a determined point in time:

~~~json
{
  "occurredAt": "2024-08-15T02:30:00Z"
}
~~~

A string with `Z` positions itself on the timeline; when displaying local time, use the recipient's zone.

### 9.3. JDBC/SQL and LocalDateTime

Database types have different semantics regarding time zones, and similarly named types can behave differently across PostgreSQL, MySQL, Oracle, and JDBC drivers. If a column stores a timestamp **without zone information**, do not assume that every value can be converted to epoch using the server's offset.

- Establish the convention for whether stored data is a UTC local representation, local time in a specific zone, or an instant with an offset.
- Check the schema, driver, session timezone configuration, and mapper.
- Test round-tripping a normal hour, a gap hour, an overlap hour, and sub-second fractions.
- Normalizing occurred-event data to `Instant`/UTC usually reduces ambiguity; civil schedules may still need to retain `ZoneId` and the original local time.

## 10. Verification formula and misconceptions to avoid

If a `LocalDateTime` has a **known, correct** `ZoneOffset`, the conceptual relationship is:

~~~text
epochSecond
    = localDateTime treated as UTC - offset.totalSeconds

Example: 2024-08-15T09:30 with offset +07:00
    = 2024-08-15T09:30Z - 7 hours
    = 2024-08-15T02:30Z
    = 1723689000 seconds since epoch
~~~

You do not need to implement this formula yourself because `toEpochSecond(offset)` and `atOffset(offset).toInstant()` already perform it safely within the supported range. The formula above is for **checking the offset sign** and understanding the meaning.

| Incorrect practice | Why it is wrong | Correct practice |
|---|---|---|
| `local.toEpochSecond(ZoneOffset.UTC)` for every `LocalDateTime`. | Only correct if the value is actually defined in UTC. | Use the data's valid offset. |
| Using New York's **current** offset for an arbitrary date. | There is DST and historical rule changes. | Look up `ZoneRules` for the local date/time. |
| Treating `ZoneId` as identical to `ZoneOffset`. | `ZoneId` has zone rules over time; offset is only a fixed difference. | Store `ZoneId` for zone-based civil time intent. |
| Calling `local.atZone(zone)` and ignoring gap/overlap. | May shift the time in a gap or silently pick the first occurrence in an overlap. | Check `getValidOffsets` and apply business policy. |
| Thinking `toEpochSecond(offset)` validates a zone's offset. | The method only uses the provided offset for calculation. | Use `ZonedDateTime.ofStrict`/`ZoneRules` if strictness is needed. |
| Multiplying epoch seconds by 1000 and assuming all nanoseconds are kept. | Sub-second fractions are lost. | Use `Instant.toEpochMilli()` when only ms are needed, or store second+nano. |
| Thinking an `Instant` always has a single local time without a zone. | The same instant renders as different times in different zones. | Convert with `instant.atZone(zone)`. |
| Storing `LocalDateTime.now()` as an absolute point in time without saving the zone. | Loses interpretation rules; cannot reliably recover the epoch later. | Record `Instant.now()` or store the zone/offset explicitly. |
| Confusing `System.nanoTime()` with epoch nanos. | Its origin is unrelated to UTC. | Use `Instant`, `currentTimeMillis`, or the appropriate epoch API. |
| Guessing whether an epoch in JSON is seconds or milliseconds. | Produces wildly wrong dates even though the number parses. | State the unit explicitly and validate the range. |

## 11. Quick decision guide

Before converting a `LocalDateTime` to an epoch, answer these in order:

1. **Does this `LocalDateTime` truly represent an event's timestamp or a local schedule?** If you already have an `Instant`, use it directly and avoid unnecessary conversions through local time.
2. **Is there a trustworthy original offset?** If yes, use `local.atOffset(offset).toInstant()` or `local.toEpochSecond(offset)`.
3. **Do you only know the geographic zone?** Use `ZoneId` and the rules at that exact date and time; do not use a fixed current offset.
4. **Does the time fall into a gap or overlap?** Choose a concrete policy: reject, adjust, prompt for offset, or pick earlier/later. If certainty is required, inspect the list of valid offsets and use `ofStrict`.
5. **What unit does the output epoch require?** Seconds, milliseconds, or preserving nanoseconds as well; state it clearly in the API/schema and ensure it does not overflow the data type.

## 12. Self-check questions

**Question 1.** Does `LocalDateTime.of(2024, 8, 15, 9, 30)` have a unique epoch?

**Answer:** No. You need a `ZoneOffset` or a `ZoneId` with resolution rules. With `+07:00`, the epoch second is `1723689000`; with UTC, the epoch is different.

**Question 2.** Why does `local.toEpochSecond(ZoneOffset.ofHours(-5))` not prove the value is valid in New York?

**Answer:** The method only uses the supplied offset for the calculation and does not check zone rules. A time in a gap can still produce an arithmetic result.

**Question 3.** How many valid epochs does `2024-11-03T01:30` in New York have?

**Answer:** Two, corresponding to `-04:00` and `-05:00`. They are 3,600 seconds apart.

**Question 4.** Does `2024-03-10T02:30` in New York have a valid epoch in New York civil time?

**Answer:** There is no valid offset for that **local time** in the zone; Java's `atZone` defaults to shifting it to `03:30-04:00`. If the user genuinely requested `02:30`, a gap-handling policy is needed.

**Question 5.** If you already have an `Instant` and want to display Vietnam time, do you need to guess an offset and change the epoch?

**Answer:** No. The epoch stays the same; use `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` to represent the same instant in the zone's date and time.

**Question 6.** What epoch milli corresponds to an instant with `epochSecond = -1` and `nano = 500000000`?

**Answer:** `-500`, which is 500 ms before the Unix epoch.

## Key takeaways

**`LocalDateTime` does not contain a UTC offset or ZoneId, so it cannot deduce a unique epoch on its own.** When the exact offset is known, use `toEpochSecond(offset)` or `atOffset(offset).toInstant()`. When the zone is known, use `ZoneId`/`ZoneRules` to determine the right offset for **that specific date and time**, and handle gaps/overlaps explicitly before creating an `Instant`. Finally, accurately distinguish **seconds, milliseconds, and nanoseconds** in storage and API communication.
