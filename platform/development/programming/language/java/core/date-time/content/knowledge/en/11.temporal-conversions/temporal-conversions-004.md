# LocalDateTime to Instant Requires an Appropriate ZoneOffset

In Java, `LocalDateTime` holds a **date and wall-clock time** (for example `2024-03-01T09:00`) but **does not contain a time zone, UTC offset, or an absolute point in time**. Conversely, `Instant` identifies a **single point in time** on the timeline, independent of whether the user is in Vietnam or New York.

To convert `LocalDateTime` to `Instant`, Java needs to know the **UTC offset (`ZoneOffset`) appropriate for that exact date and time**:

```java
LocalDateTime local = LocalDateTime.of(2024, 3, 1, 9, 0);
ZoneOffset offset = ZoneOffset.of("+07:00");
Instant instant = local.toInstant(offset);
// 2024-03-01T02:00:00Z
```

This illustrative snippet requires `import java.time.*;`. `toInstant(offset)` **does not look up a time zone automatically** and **does not verify whether the offset actually belongs to a city**. It applies the offset provided by the caller. If the wrong offset is chosen, the code may run normally, but the resulting `Instant` is semantically wrong for the business logic.

> **Principle:** `LocalDateTime + ZoneOffset → Instant` is only correct when the offset has been determined by reliable data or rules. If the business logic refers to a **location's time zone**, use `ZoneId` and `ZoneRules` to obtain/check the offset at the **specific date and time**, especially around DST.

## 1. Why Can't LocalDateTime Infer Instant on Its Own?

The same local date and time string `2024-03-01T09:00` can represent **many different UTC instants**:

| LocalDateTime | Applied Offset | Corresponding Instant |
| --- | --- | --- |
| `2024-03-01T09:00` | `+07:00` | `2024-03-01T02:00:00Z` |
| `2024-03-01T09:00` | `Z` / `+00:00` | `2024-03-01T09:00:00Z` |
| `2024-03-01T09:00` | `-05:00` | `2024-03-01T14:00:00Z` |

All three `LocalDateTime` values have the same date, hour, and minute. What differs is the offset information **supplied from the outside**.

Conceptual formula:

```text
Instant (UTC) = LocalDateTime - ZoneOffset
```

With `09:00+07:00`, we **subtract** 7 hours from 09:00 to get 02:00 UTC. With `09:00-05:00`, we **add** 5 hours to 09:00 to get 14:00 UTC. The sign of the offset is especially easy to confuse:

- `+07:00`: local time is 7 hours ahead of UTC.
- `-05:00`: local time is 5 hours behind UTC.
- `Z`: 0 seconds difference, equivalent to `ZoneOffset.UTC`.

A `LocalDateTime` has no offset field; by itself, it cannot decide which of the above results is correct.

### Concepts to Distinguish

| Java Type | What Does It Contain? | Can It Identify a Single Point in Time on Its Own? |
| --- | --- | --- |
| `LocalDateTime` | Date, hour, minute, second, nanosecond | **No** |
| `ZoneOffset` | Fixed number of seconds offset from UTC | **No** on its own |
| `Instant` | An absolute point on the timeline | **Yes** |
| `OffsetDateTime` | LocalDateTime + ZoneOffset | **Yes**, can be converted to `Instant` |
| `ZonedDateTime` | Date-time + ZoneId + resolved offset | **Yes**, can be converted to `Instant` |
| Region-based `ZoneId` | An ID like `America/New_York` with rules that change over time | Not sufficient without a date-time/instant |

`ZoneOffset` is a subtype of `ZoneId`, but a **fixed offset is not equivalent to a geographical time zone**. `-05:00` may be valid in New York on a winter day, but not on some summer days.

## 2. Direct API: LocalDateTime.toInstant(ZoneOffset)

Method:

```java
Instant instant = localDateTime.toInstant(offset);
```

- `localDateTime`: date/time in the ISO calendar, without time-zone information.
- `offset`: `java.time.ZoneOffset`, the UTC offset that you **explicitly specify**.
- Return value: `java.time.Instant`, preserving nanosecond precision.
- `LocalDateTime` is not modified because these `java.time` types are immutable.
- If `offset == null`, the method cannot perform the conversion; a real offset must be passed, not `null` as a substitute for "let the machine choose".

Example with an offset confirmed by the contract:

```java
import java.time.*;

LocalDateTime entered = LocalDateTime.of(2024, 3, 1, 9, 0);
ZoneOffset knownOffset = ZoneOffset.ofHours(7);

Instant instant = entered.toInstant(knownOffset);
System.out.println(instant); // 2024-03-01T02:00:00Z
```

This snippet illustrates the call and needs to be placed inside a method. It is **semantically correct** if the data source guarantees that "09:00" is in time with offset `+07:00`. If the source only states "09:00 New York", assigning `+07:00` is wrong even though the program still produces an `Instant`.

### When Can You Pass ZoneOffset Directly?

- The payload has a reliable offset field, such as `2024-03-01T09:00:00+07:00`.
- The protocol clearly defines every `LocalDateTime` in that field as **UTC time**; in that case, use `ZoneOffset.UTC`.
- A fixed device or business contract **genuinely uses a fixed offset**, without requiring calculation according to regional time-zone rules.
- You are converting an existing `OffsetDateTime` value; it is better to use `offsetDateTime.toInstant()` directly rather than splitting the offset and local time and recombining them.

You should not choose an offset based on habit, server location, user locale, or the "current" offset of a city when the data belongs to a different date.

## 3. A Wrong Offset Choice Produces the Wrong Instant Without Any Java Error

Consider the same input time `2024-03-01T09:00`:

```java
LocalDateTime local = LocalDateTime.of(2024, 3, 1, 9, 0);

Instant correctIfPlus7 = local.toInstant(ZoneOffset.of("+07:00"));
Instant mistakenIfUtc = local.toInstant(ZoneOffset.UTC);

System.out.println(correctIfPlus7); // 2024-03-01T02:00:00Z
System.out.println(mistakenIfUtc);   // 2024-03-01T09:00:00Z
```

This illustrative snippet requires `import java.time.*;`. The two results differ by **7 hours**. Java cannot know which contract is right, so it throws no exception; the responsibility lies in determining the **meaning of the source data**.

A similar mistake is:

```java
// WARNING: only correct if "local" is actually defined as UTC time!
Instant assumedUtc = local.toInstant(ZoneOffset.UTC);
```

Do not attach `UTC` just because the application runs on a UTC server. The operating system time zone does not define the time zone of the **time the user entered**.

## 4. When Data Has a Region Name, Look Up the Offset by Zone and Date-Time

Suppose a user schedules an appointment for **09:00 in New York**. The `America/New_York` zone changes its offset between winter and summer. Using `ZoneId` matches the intent of "local time in New York":

```java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime winter = LocalDateTime.of(2024, 1, 15, 9, 0);
LocalDateTime summer = LocalDateTime.of(2024, 7, 15, 9, 0);

ZonedDateTime winterZoned = winter.atZone(newYork);
ZonedDateTime summerZoned = summer.atZone(newYork);

System.out.println(winterZoned.getOffset()); // -05:00
System.out.println(summerZoned.getOffset()); // -04:00

System.out.println(winterZoned.toInstant());
// 2024-01-15T14:00:00Z
System.out.println(summerZoned.toInstant());
// 2024-07-15T13:00:00Z
```

This illustrative snippet requires `import java.time.*;`. Both appointments are **09:00 in New York**, yet the offset is determined from the zone rules on two different dates. For this requirement, the direct approach is usually:

```java
Instant instant = local.atZone(zone).toInstant();
```

The `local` variable must be a `LocalDateTime`, and `zone` is a properly chosen `ZoneId`. The call above uses the **default rules** of `atZone` to handle local times when DST creates a gap/overlap. If the application must **reject non-existent times or make the user choose one of two offsets**, those cases must be handled separately (section 5).

### Using ZoneRules When Full Control Is Needed

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 0);

List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
// List contains one offset: -04:00

ZoneOffset offset = valid.get(0);
Instant instant = local.toInstant(offset);
// 2024-07-15T13:00:00Z
```

This illustrative snippet requires `import java.time.*;` and `import java.util.List;`. Only call `get(0)` like this when you have **verified** that the list has exactly one element. At a DST boundary, the list may have **0 or 2 elements**; do not accidentally trigger an `IndexOutOfBoundsException` or pick an unconfirmed business option.

## 5. DST: An "Appropriate ZoneOffset" May Not Exist or May Not Be Unique

Converting from `LocalDateTime` to `Instant` according to a **geographical zone** has three distinct cases. Query `zone.getRules().getValidOffsets(local)` to get the valid offsets for **this exact date/time**:

| Number of Valid Offsets | Status | Meaning |
| --- | --- | --- |
| 1 | Normal time | Exactly one corresponding `Instant` exists |
| 0 | *Gap* | The wall-clock time does not exist in the zone on that date |
| 2 | *Overlap* | A wall-clock time occurs twice with two offsets |

### 5.1. Gap: No Valid Offset

In New York on **2024-03-10**, clocks jump from 01:59:59 to 03:00. Therefore, `2024-03-10T02:30` is a valid `LocalDateTime` in the ISO calendar, but **does not exist as a New York local time**.

```java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);

List<ZoneOffset> offsets =
        newYork.getRules().getValidOffsets(gap);

System.out.println(offsets); // []
```

This illustrative snippet requires `java.time.*` and `java.util.List`. If you call:

```java
ZonedDateTime adjusted = gap.atZone(newYork);
System.out.println(adjusted);
// 2024-03-10T03:30-04:00[America/New_York]
```

`atZone` uses a default policy that **pushes a time falling in a gap forward by the gap duration**. This may be an acceptable behavior for some calendar features, but **you must not silently change a 02:30 appointment to 03:30** if the user or business contract requires rejecting non-existent times.

More importantly, `gap.toInstant(ZoneOffset.of("-05:00"))` **still produces an `Instant`** because `toInstant(offset)` only uses the passed-in offset; it does not know the constraints of `America/New_York`. The resulting instant will correspond to **03:30 in New York** on that day, not 02:30 as originally intended. Thus, you cannot rely on the conversion succeeding to conclude that the offset fits the zone.

When **strict mode** (*strict*) is needed:

```java
ZonedDateTime.ofStrict(
        gap, ZoneOffset.of("-05:00"), newYork);
// Throws DateTimeException because -05:00 is not valid
// for this LocalDateTime in America/New_York.
```

The illustrative call intentionally throws an exception; to continue execution, you must catch `DateTimeException`. In this example, **there is no valid offset** for 02:30 in the New York zone.

### 5.2. Overlap: Two Valid Offsets

On **2024-11-03** in New York, clocks fall back, so `01:30` occurs **twice**, once at `-04:00` and once at `-05:00`.

```java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2024, 11, 3, 1, 30);

List<ZoneOffset> offsets =
        newYork.getRules().getValidOffsets(repeated);

System.out.println(offsets); // [-04:00, -05:00]

Instant first = repeated.toInstant(offsets.get(0));
Instant second = repeated.toInstant(offsets.get(1));

System.out.println(first);  // 2024-11-03T05:30:00Z
System.out.println(second); // 2024-11-03T06:30:00Z
```

This illustrative snippet requires `import java.time.*;` and `import java.util.List;`. The two results are **one real hour apart**, even though `LocalDateTime` has the same value. If this matters for orders, flights, payments, or notifications, store the chosen offset (or the resolved `Instant`) so the data is unambiguous.

By default, `repeated.atZone(newYork)` usually selects the **earlier offset**, which in this example is `-04:00`; `withLaterOffsetAtOverlap()` switches to the later offset if needed. This is the API's default policy, not necessarily the business rule you want.

### 5.3. Explicit Resolution Strategy

If the input consists of `LocalDateTime` and `ZoneId`, a strict business workflow is:

1. Get `List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local)`.
2. If the list is **empty**: reject the non-existent time or apply a **clearly documented** adjustment policy.
3. If there is **one element**: use that offset, for example `local.toInstant(offsets.get(0))`.
4. If there are **two elements**: ask the user to choose or apply an agreed "earlier/later" rule; store the choice.
5. You can use `ZonedDateTime.ofStrict(local, chosenOffset, zone)` to verify that the chosen offset is **valid for that local date-time and zone**. Once you have a valid `ZonedDateTime`, call `toInstant()`.

Do not try to use `zone.getRules().getOffset(Instant.now())` to compute the offset for an appointment on another day. The offset must be determined for the **date and time of the appointment**, not at the time the program runs.

## 6. Complete, Verified Java 17+ Example

Create the file **`LocalDateTimeToInstantDemo.java`**:

```java
import java.time.*;
import java.util.List;

public class LocalDateTimeToInstantDemo {
    public static void main(String[] args) {
        LocalDateTime vietnamLocal = LocalDateTime.of(2024, 3, 1, 9, 0);
        ZoneOffset vietnamOffset = ZoneOffset.of("+07:00");

        Instant instant = vietnamLocal.toInstant(vietnamOffset);
        System.out.println("Vietnam local: " + vietnamLocal);
        System.out.println("With +07:00: " + instant);
        System.out.println("Mistaken as UTC: " + vietnamLocal.toInstant(ZoneOffset.UTC));
        System.out.println("Round trip: "
                + LocalDateTime.ofInstant(instant, vietnamOffset));

        ZoneId newYork = ZoneId.of("America/New_York");
        LocalDateTime winter = LocalDateTime.of(2024, 1, 15, 9, 0);
        LocalDateTime summer = LocalDateTime.of(2024, 7, 15, 9, 0);
        ZoneOffset winterOffset = newYork.getRules().getValidOffsets(winter).get(0);
        ZoneOffset summerOffset = newYork.getRules().getValidOffsets(summer).get(0);
        System.out.println("NY winter offset: " + winterOffset);
        System.out.println("NY summer offset: " + summerOffset);
        System.out.println("NY winter instant: " + winter.toInstant(winterOffset));
        System.out.println("NY summer instant: " + summer.toInstant(summerOffset));

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("NY gap valid offsets: "
                + newYork.getRules().getValidOffsets(gap));
        System.out.println("NY gap atZone: " + gap.atZone(newYork));
        try {
            ZonedDateTime.ofStrict(gap, ZoneOffset.of("-05:00"), newYork);
            System.out.println("NY gap ofStrict: accepted");
        } catch (DateTimeException ex) {
            System.out.println("NY gap ofStrict: rejected");
        }

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> candidates = newYork.getRules().getValidOffsets(overlap);
        System.out.println("NY overlap offsets: " + candidates);
        System.out.println("NY overlap first instant: " + overlap.toInstant(candidates.get(0)));
        System.out.println("NY overlap second instant: " + overlap.toInstant(candidates.get(1)));
    }
}
```

In the directory containing the file:

```bash
javac LocalDateTimeToInstantDemo.java
java LocalDateTimeToInstantDemo
```

**Exact stdout**, verified with `javac --release 17` and `java`:

```text
Vietnam local: 2024-03-01T09:00
With +07:00: 2024-03-01T02:00:00Z
Mistaken as UTC: 2024-03-01T09:00:00Z
Round trip: 2024-03-01T09:00
NY winter offset: -05:00
NY summer offset: -04:00
NY winter instant: 2024-01-15T14:00:00Z
NY summer instant: 2024-07-15T13:00:00Z
NY gap valid offsets: []
NY gap atZone: 2024-03-10T03:30-04:00[America/New_York]
NY gap ofStrict: rejected
NY overlap offsets: [-04:00, -05:00]
NY overlap first instant: 2024-11-03T05:30:00Z
NY overlap second instant: 2024-11-03T06:30:00Z
```

The results demonstrate:

- With the correct `+07:00` offset → 09:00 local corresponds to 02:00 UTC.
- Mistakenly assigning `UTC` throws no error but produces an `Instant` 7 hours off.
- For the same `LocalDateTime` 09:00 in New York, the winter and summer offsets differ.
- A DST gap has **0 valid offsets**; `atZone` adjusts the time, whereas `ofStrict` rejects it.
- A DST overlap has **2 valid offsets**, hence two different candidate `Instant`s.

**Note:** Calling `get(0)` in the winter/summer example intentionally picked two normal times that have exactly one valid offset. Do not copy that pattern for arbitrary dates/times without considering gaps/overlaps.

## 7. Equivalent Conversion Paths and When to Choose Each

### 7.1. LocalDateTime + ZoneOffset

```java
Instant instantA = local.toInstant(offset);
```

The most concise approach when you **already have the appropriate offset**. The source data must guarantee the offset, because this API does not look up zone rules automatically.

### 7.2. Via OffsetDateTime

```java
OffsetDateTime value = local.atOffset(offset);
Instant instantB = value.toInstant();
```

`instantA.equals(instantB)` will be `true` when both are created from the same `local` and `offset`. `OffsetDateTime` is useful when you need to keep both the **local date-time and the offset** in an object/API, such as the string `2024-03-01T09:00:00+07:00`.

### 7.3. Via ZonedDateTime with ZoneId

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instantC = local.atZone(zone).toInstant();
```

Suitable when the input is the **time in a specific region**, requiring DST/historical rules. However, `atZone` has a **default gap/overlap resolution rule**. If the application requires strict validation, use `getValidOffsets` and `ZonedDateTime.ofStrict` as shown in section 5.

### 7.4. Instant → LocalDateTime: Must Know Zone or Offset

The reverse conversion has no single "canonical local time":

```java
Instant instant = Instant.parse("2024-03-01T02:00:00Z");

LocalDateTime atPlusSeven =
        LocalDateTime.ofInstant(instant, ZoneOffset.of("+07:00"));
// 2024-03-01T09:00

LocalDateTime atUtc =
        LocalDateTime.ofInstant(instant, ZoneOffset.UTC);
// 2024-03-01T02:00
```

This illustrative snippet requires `import java.time.*;`. The same `Instant` can be displayed as different `LocalDateTime` values depending on the zone. **A round trip preserves the local date-time only when using the same offset**:

```java
LocalDateTime original = LocalDateTime.of(
        2024, 3, 1, 9, 0, 123_456_789);
ZoneOffset offset = ZoneOffset.of("+07:00");

LocalDateTime restored = LocalDateTime.ofInstant(
        original.toInstant(offset), offset);

System.out.println(restored.equals(original)); // true
```

Nanosecond precision is preserved during `LocalDateTime ↔ Instant` conversion if the value is within the range supported by `Instant` and the appropriate offset is used. This snippet is also just an example inside a Java method.

## 8. Why Shouldn't You Pick ZoneOffset from the "Current Time Zone"?

Suppose an employee enters an appointment in New York for **July**, while the server is running in **January**. Getting New York's offset at `Instant.now()` will return `-05:00` in January, whereas the July appointment needs `-04:00`. As a result, the appointment will be off by one hour.

Example **to avoid**:

```java
// Error-prone: offset is obtained at the current time, not the appointment date.
ZoneOffset currentOffset = zone.getRules().getOffset(Instant.now());
Instant appointment = local.toInstant(currentOffset);
```

This is illustrative code with `zone` and `local` already declared; it also depends on the system clock at runtime, making tests flaky. A safer approach:

```java
List<ZoneOffset> candidates = zone.getRules().getValidOffsets(local);

if (candidates.size() == 1) {
    Instant appointment = local.toInstant(candidates.get(0));
    // Use appointment according to business logic.
} else {
    // 0: non-existent time; 2: repeated time.
    // Apply the designed policy, do not guess the offset.
}
```

The illustrative snippet above sits inside a method, with `zone: ZoneId` and `local: LocalDateTime` already available; it requires `java.time.*` and `java.util.List`. If the business logic **deliberately** chooses the default rules of `atZone`, you can also use `local.atZone(zone).toInstant()`, but be fully aware of that behavior.

## 9. Receiving Timestamps from an API: Parse According to Available Data

Distinguish inputs:

| String | Available Information | Appropriate Java Type |
| --- | --- | --- |
| `2024-03-01T09:00:00` | Date + time, no offset | `LocalDateTime` |
| `2024-03-01T09:00:00+07:00` | Date + time + offset | `OffsetDateTime` |
| `2024-03-01T02:00:00Z` | A UTC point in time | `Instant` |
| `2024-03-01T09:00:00+07:00[Asia/Ho_Chi_Minh]` | Date-time + zone + offset | `ZonedDateTime` |

Example when the API already provides an offset:

```java
OffsetDateTime received =
        OffsetDateTime.parse("2024-03-01T09:00:00+07:00");

Instant instant = received.toInstant();
// 2024-03-01T02:00:00Z
```

This illustrative snippet requires `import java.time.*`. Do not parse a payload that already has an offset and then call `toLocalDateTime()`, discarding the offset, unless the business logic genuinely only wants the wall-clock date/time. If you later try to reconstruct an `Instant` from a `LocalDateTime` that lost its offset, the original point in time may be **unrecoverable**.

If the API only has `LocalDateTime`, you must **supplement the zone/offset per the contract** before converting. Do not use `ZoneId.systemDefault()` or `ZoneOffset.UTC` as a "safe default" if the actual data does not indicate that.

### Storing Events and Appointments

- **Events that have already occurred** such as `createdAt`, `paidAt`, `sentAt`: usually stored as `Instant` or a UTC timestamp with a clear DB/driver convention; displayed via `instant.atZone(viewerZone)`.
- **Future appointments by location**: usually store **`LocalDateTime + ZoneId`** and the DST handling rule to preserve the intent of "09:00 in Paris". You can also store the resolved `Instant` if needed to execute notifications/bookings accurately.
- **Protocols carrying an actual offset**: `OffsetDateTime` preserves the message's original offset; call `toInstant()` when synchronizing events.

Data type names such as `TIMESTAMP`, `DATETIME`, or `TIMESTAMP WITH TIME ZONE` do not behave identically across all databases. You need to verify how the driver/JPA/JDBC writes and reads them, avoiding the assumption that the DB will automatically preserve IANA zones or UTC according to contract.

## 10. Common Mistakes and How to Spot Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Calling `local.toInstant(ZoneOffset.UTC)` for all inputs | Events are shifted if source time is not UTC | Use a confirmed offset or resolve `ZoneId` |
| Choosing `+07:00` just because the server is in Vietnam | Source time may belong to another zone | Get zone/offset from business data |
| Using New York's winter offset for summer | Off by one hour | Look up `ZoneRules` by date-time |
| Using `getValidOffsets(local).get(0)` without checking size | Crashes on gaps; picks arbitrarily on overlaps | Handle all three cases: 0/1/2 |
| Treating `toInstant` as time-zone validation | Offset does not need to be valid for a specific zone | Use `ofStrict` or check rules |
| Thinking `LocalDateTime` already contains an `Instant` | Missing offset/zone | Provide confirmed information |
| Confusing the sign of the offset | UTC off by many hours | `Instant = local - offset` |
| Using `Instant.now()` to pick the offset for an appointment date | Wrong when the season/time differs | Look up by `LocalDateTime` or create `ZonedDateTime` per policy |
| Storing only `LocalDateTime` for cross-zone transactions | Cannot recover the exact point in time | Store `Instant` or both offset/zone |
| Appending `Z` directly to a local time string | Assigns wrong UTC meaning | Convert with the right offset, then format `Instant` |
| Confusing an offset with a city's `ZoneId` | Loses DST and historical rules | Use IANA ID when business logic is regional |
| Assuming every local day is exactly 24 hours long | DST can make a real day 23 or 25 hours | Use `ZonedDateTime` / `Instant` to compute actual duration |

## 11. Testing Checklist

| Test Case | Check | Expected Result |
| --- | --- | --- |
| Offset +07:00 | `LocalDateTime.of(2024,3,1,9,0).toInstant(+07:00)` | `2024-03-01T02:00:00Z` |
| Offset UTC | Same local time above with `UTC` | `2024-03-01T09:00:00Z` |
| Negative offset -05:00 | Same local time with `-05:00` | `2024-03-01T14:00:00Z` |
| New York winter time | `2024-01-15T09:00` | `-05:00` → `14:00Z` |
| New York summer time | `2024-07-15T09:00` | `-04:00` → `13:00Z` |
| DST gap | `2024-03-10T02:30` New York | 0 valid offsets; `ofStrict` rejects |
| DST overlap | `2024-11-03T01:30` New York | 2 offsets, 2 different `Instant`s |
| Round trip with same offset | `LocalDateTime → Instant → LocalDateTime` | Preserves original value, including nanoseconds |
| Round trip with different offset | Convert back to local time with a different offset | Date/local time may differ |
| ISO payload with offset | Parse `OffsetDateTime` | Preserves offset and computes correct `Instant` |
| Out-of-range offset | `ZoneOffset.of("+19:00")` | Throws `DateTimeException` |

In JUnit 5, a test can use `assertEquals` to compare two expected `Instant`s and `assertThrows(DateTimeException.class, ...)` when ensuring `ZonedDateTime.ofStrict` rejects an invalid offset according to zone rules. Test cases at DST boundaries are more valuable than only testing normal midday times.

## 12. Quick Conversion Path Selection

| Information You Have | Desired Result | Appropriate Approach |
| --- | --- | --- |
| `LocalDateTime` + verified `ZoneOffset` | `Instant` | `local.toInstant(offset)` |
| `LocalDateTime` + `ZoneOffset` | Date/time still accompanied by offset | `local.atOffset(offset)` |
| `OffsetDateTime` | `Instant` | `value.toInstant()` |
| `LocalDateTime` + regional `ZoneId` | `Instant` with default policy | `local.atZone(zone).toInstant()` |
| `LocalDateTime` + `ZoneId`, strict on DST | Unambiguous `Instant` | Check `getValidOffsets`, pick valid one, optionally `ofStrict` |
| `Instant` + `ZoneOffset` | `LocalDateTime` | `LocalDateTime.ofInstant(instant, offset)` |
| `Instant` + regional `ZoneId` | `ZonedDateTime` | `instant.atZone(zone)` |
| Two `Instant`s | Actual duration | `Duration.between(start, end)` |

**Key Takeaway:** `LocalDateTime` describes a **wall-clock time**, whereas `Instant` describes an **absolute point in time**. Calling `local.toInstant(offset)` is only correct when **`ZoneOffset` actually matches the data source**. If the time is tied to a city, use `ZoneId` and the rules for that date; at DST gaps/overlaps, an explicit decision must be made rather than guessing.