# Converting `ZonedDateTime` to `OffsetDateTime` and Information Loss

In Java, `ZonedDateTime` represents a date-time associated with a **time zone** (`ZoneId`) and an offset resolved according to that zone's rules at that point in time. `OffsetDateTime` only holds **a local date-time + a fixed offset from UTC**; it does not retain the geographical region name or its historical, DST, or future offset transition rules.

The `ZonedDateTime.toOffsetDateTime()` method is very useful when exchanging timestamps that already include an offset, but this conversion **does not preserve the full time-zone semantics**. Specifically:

- **Retained:** year, month, day, hour, minute, second, and nanosecond of the local value; the current offset; and the corresponding point in time (`Instant`).
- **Lost:** the region `ZoneId` such as `America/New_York` or `Europe/Berlin`, if the source uses a region ID; and the ability to directly query the zone's history and offset transition rules from the resulting `OffsetDateTime` itself.
- **Consequence:** the current timestamp remains accurate, but future scheduling or adding days across DST transitions may differ when only a fixed offset remains.

This is an example of a **lossy conversion** with respect to time-zone semantics, even though it does not lose nanoseconds or change the `Instant` at the moment of conversion.

## 1. Reviewing the Role of Each Type

| Type | Holds local date-time | Holds offset | Holds rule-based zone ID | Determines `Instant` |
| --- | --- | --- | --- | --- |
| `LocalDateTime` | Yes | No | No | Not yet |
| `OffsetDateTime` | Yes | Yes, fixed in the value | No | Yes |
| `ZonedDateTime` with IANA zone | Yes | Yes, resolved from the zone at that date-time | Yes | Yes |
| `Instant` | Does not represent separate local fields | No | No | Is the point in time itself |

For example, two zone IDs `America/New_York` and `America/Toronto` can share the same `-05:00` offset on 2024-01-15. Converting a `ZonedDateTime` from either one to `OffsetDateTime` can produce **the exact same value**. There is no mathematical way to recover the exact original zone name from just the date-time and offset: multiple zones may match.

It is also important to distinguish `ZoneOffset` from `ZoneId`:

- `ZoneOffset.of("-05:00")` is a **fixed** offset of UTC−05:00.
- `ZoneId.of("America/New_York")` is a region zone ID with **a set of rules**: January 2024 is `-05:00`, whereas July 2024 is `-04:00`.
- A `ZonedDateTime` can also use a `ZoneOffset` as its `ZoneId`. When the source only has a fixed offset to begin with, there is no IANA region identity to lose. This lesson focuses on the case where the source has an actual region zone ID.

## 2. Converting with `toOffsetDateTime()`

```java
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime zoned = ZonedDateTime.of(
        2024, 1, 15, 9, 0, 0, 0, zone);

OffsetDateTime offset = zoned.toOffsetDateTime();

System.out.println(zoned);
// 2024-01-15T09:00-05:00[America/New_York]

System.out.println(offset);
// 2024-01-15T09:00-05:00
```

`toOffsetDateTime()` takes the date-time fields and **the offset at the given point in time** from the `ZonedDateTime`. The result is an immutable value type. No time shifting or local time recalculation occurs during the conversion; `zoned` is not modified either.

Conceptual diagram:

```text
ZonedDateTime
2024-01-15T09:00-05:00[America/New_York]
       |
       | toOffsetDateTime()
       v
OffsetDateTime
2024-01-15T09:00-05:00
                 |
                 +-- local date/time: retained
                 +-- offset -05:00: retained
                 +-- Instant 14:00Z: retained
                 +-- "America/New_York": LOST
                 +-- zone DST rules: no longer in the value
```

From an `OffsetDateTime` value, calling `toInstant()` is still accurate because the date, time, and offset are sufficient to compute the UTC instant.

```java
System.out.println(zoned.toInstant());
// 2024-01-15T14:00:00Z

System.out.println(offset.toInstant());
// 2024-01-15T14:00:00Z

System.out.println(zoned.toInstant().equals(offset.toInstant()));
// true
```

**Key takeaway:** "Losing the zone" is **not** "losing the offset." These two concepts differ in both data and semantics.

## 3. Inventory Table: What Exactly Is Retained and Lost?

| Property of original `zoned` | Status after `toOffsetDateTime()` | How to verify |
| --- | --- | --- |
| ISO date | Retained | `toLocalDate()` |
| Local time (down to nanoseconds) | Retained | `toLocalTime()`, `getNano()` |
| Offset at that point in time | Retained | `getOffset()` |
| Absolute point in time | Retained | `toInstant()` |
| Zone ID `America/New_York` | **Not retained** | `OffsetDateTime` has no `getZone()` |
| Seasonal/historical offset transition rules | **Not retained as a zone** | `OffsetDateTime` only carries `ZoneOffset` |
| Ability to know the zone's offset on another date | **Cannot be uniquely inferred** | Requires the actual `ZoneId` and zone rule data |
| Original locale/display name info | Not stored by either type | Must manage locale/format separately |

If you are processing a record that **already happened**, `OffsetDateTime` can be completely sufficient for sending an accurate timestamp. If you are handling "every day at 09:00 in New York," an offset taken from a single day **cannot** replace the zone ID for subsequent scheduled occurrences.

### `equals()` and `toInstant()` Answer Different Questions

`ZonedDateTime.equals(...)` checks the date-time value, offset, and zone within the **same type**. After converting to `OffsetDateTime`, you cannot compare them directly with `equals` and expect them to be equal as objects/types:

```java
boolean sameObjectValue = zoned.equals(offset);   // false
boolean sameInstant = zoned.toInstant()
        .equals(offset.toInstant());               // true
```

To compare **points in time**, convert both to `Instant`. Do not treat `equals()` across different types as a check for whether the instant was preserved.

## 4. Can `OffsetDateTime` Be Converted Back to `ZonedDateTime`?

**You can convert the type, but it does not automatically restore the original zone.**

`OffsetDateTime.toZonedDateTime()` creates a `ZonedDateTime` whose **zone is simply the current offset**, without knowing the `America/New_York` zone from the source data.

```java
OffsetDateTime offset = zoned.toOffsetDateTime();
ZonedDateTime fromOffset = offset.toZonedDateTime();

System.out.println(fromOffset);
// 2024-01-15T09:00-05:00

System.out.println(fromOffset.getZone());
// -05:00

System.out.println(zoned.equals(fromOffset));
// false

System.out.println(zoned.toInstant().equals(fromOffset.toInstant()));
// true
```

The result is still a valid `ZonedDateTime`, but `getZone()` is the `ZoneOffset` `-05:00` rather than the `America/New_York` region. This is **not a lossless restoration**.

### If the Original `ZoneId` Is Still Stored

When the system knows the exact zone ID from a separate data field, it can be reattached via:

```java
ZoneId originalZone = ZoneId.of("America/New_York");

ZonedDateTime recovered = offset.atZoneSameInstant(originalZone);

System.out.println(recovered);
// 2024-01-15T09:00-05:00[America/New_York]

System.out.println(recovered.toInstant()
        .equals(offset.toInstant()));
// true
```

`OffsetDateTime.atZoneSameInstant(zone)` **preserves the instant**, then expresses it using the rules of the provided zone. This is a conversion that supplies **external information** beyond the `OffsetDateTime`, not an inference of the zone from the offset.

Be careful: if you attach a different zone, the result is still the **same instant**, but the date/time and offset may change.

```java
System.out.println(offset.atZoneSameInstant(ZoneId.of("Asia/Tokyo")));
// 2024-01-15T23:00+09:00[Asia/Tokyo]
```

Here, the Tokyo zone is a **new choice made by the application**; it does not prove that the original event occurred in Tokyo.

### `atZoneSimilarLocal(...)` Is Not the Same as `atZoneSameInstant(...)`

Java also provides `OffsetDateTime.atZoneSimilarLocal(zone)`, whose goal is to **try to keep the local date-time** when attaching a new zone; if the old offset is valid in that zone at that local time, it prefers keeping it, otherwise it resolves according to the zone's rules. It **can change the instant**.

For example, attaching `2024-01-15T09:00-05:00` to Tokyo:

```java
ZoneId tokyo = ZoneId.of("Asia/Tokyo");

ZonedDateTime sameInstant = offset.atZoneSameInstant(tokyo);
ZonedDateTime similarLocal = offset.atZoneSimilarLocal(tokyo);

System.out.println(sameInstant);
// 2024-01-15T23:00+09:00[Asia/Tokyo]

System.out.println(similarLocal);
// 2024-01-15T09:00+09:00[Asia/Tokyo]
```

One keeps the same instant, while the other keeps the same 09:00 wall-clock time; do **not** use `atZoneSimilarLocal` merely to change the display time zone of an already-occurred transaction. In gaps or overlaps, `ZonedDateTime` resolution rules can also adjust the hour or offset.

## 5. The Same Offset Does Not Identify a Unique Zone

Suppose two meetings take place at 09:00 on 2024-01-15 in New York time and Toronto time, respectively:

```java
ZonedDateTime newYork = ZonedDateTime.of(
        2024, 1, 15, 9, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime toronto = ZonedDateTime.of(
        2024, 1, 15, 9, 0, 0, 0,
        ZoneId.of("America/Toronto"));

System.out.println(newYork.toOffsetDateTime()
        .equals(toronto.toOffsetDateTime()));
// true

System.out.println(newYork.getZone().equals(toronto.getZone()));
// false
```

On that date, both zones have `-05:00`. `OffsetDateTime` has no way to distinguish New York from Toronto. The same situation occurs among many other zones around the world, even when their current rules overlap: the zone name remains distinct **contextual data**.

Using `ZoneId` is also important when two zones share the same offset today but **differ in historical, DST, or future policies**. Knowing only `-05:00` at 09:00 does not tell you what that zone's offset will be on another specific date.

## 6. Practical Consequence: Adding One Day Across DST

Consider New York before the daylight saving time transition on **2024-03-10**. On March 9, the offset is `-05:00`; by noon on March 10, it is `-04:00`.

```java
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, ny);

ZonedDateTime zonedNextDay = start.plusDays(1);
OffsetDateTime offsetOnly = start.toOffsetDateTime();
OffsetDateTime offsetNextDay = offsetOnly.plusDays(1);

System.out.println(start);
// 2024-03-09T12:00-05:00[America/New_York]

System.out.println(zonedNextDay);
// 2024-03-10T12:00-04:00[America/New_York]

System.out.println(offsetOnly);
// 2024-03-09T12:00-05:00

System.out.println(offsetNextDay);
// 2024-03-10T12:00-05:00
```

Both `plusDays(1)` calls advance the local date by one, but:

- `ZonedDateTime.plusDays(1)` uses **New York's zone rules** for the new date and applies the `-04:00` offset.
- `OffsetDateTime.plusDays(1)` simply keeps the **fixed `-05:00` offset**, because the `OffsetDateTime` value itself has no zone ID or DST rules to update automatically.

```text
Source 2024-03-09 12:00 New York:
    2024-03-09T12:00-05:00 = 17:00Z

Correct "tomorrow 12:00 New York":
    2024-03-10T12:00-04:00 = 16:00Z
    => 23 actual hours elapsed

If zone was dropped, keeping only offset -05:00:
    2024-03-10T12:00-05:00 = 17:00Z
    => 24 actual hours elapsed
```

Therefore, converting to `OffsetDateTime` is **safe for storing the timestamp of a specific past or single-point event**, but can cause bugs when you want to **continue doing calendar arithmetic according to local rules**.

If you cross into **autumn** when New York leaves DST (2024-11-03), the effect works in the opposite direction: one calendar day between two noons can be **25 hours** long, whereas adding a day on `OffsetDateTime` with a fixed offset still spans 24 hours.

### Why Is This Not Just "Losing a Display Name"?

Losing `ZoneId` loses the data needed to **determine future offsets**, not just a decorative string in a log. `OffsetDateTime` does not know when New York switches from `-05:00` to `-04:00`. Consequently, daily notification schedules, recurring meetings, and deadlines defined as "tomorrow at the same local time" can drift.

Note that IANA zones can change policies based on government decisions and tzdb updates. For future schedules, keeping `ZoneId` lets the system use the zone's rules according to current time-zone data; you should also plan for updating and recalculating schedules when rules change.

## 7. Complete Java 17+ Example (Standalone, Runnable)

Create the file **`ZonedToOffsetDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ZonedToOffsetDemo {
    public static void main(String[] args) {
        ZoneId newYorkZone = ZoneId.of("America/New_York");
        ZoneId torontoZone = ZoneId.of("America/Toronto");

        ZonedDateTime original = ZonedDateTime.of(
                2024, 1, 15, 9, 0, 0, 0, newYorkZone);
        OffsetDateTime converted = original.toOffsetDateTime();

        System.out.println("original = " + original);
        System.out.println("converted = " + converted);
        System.out.println("same instant = "
                + original.toInstant().equals(converted.toInstant()));
        System.out.println("offset retained = "
                + original.getOffset().equals(converted.getOffset()));
        System.out.println("nano retained = "
                + (original.getNano() == converted.getNano()));

        ZonedDateTime rebuiltWithoutRegion = converted.toZonedDateTime();
        System.out.println("rebuilt without region = "
                + rebuiltWithoutRegion);
        System.out.println("rebuilt zone = "
                + rebuiltWithoutRegion.getZone());
        System.out.println("original equals rebuilt = "
                + original.equals(rebuiltWithoutRegion));

        ZonedDateTime recoveredWithZone =
                converted.atZoneSameInstant(newYorkZone);
        System.out.println("restored with explicit zone = "
                + recoveredWithZone);
        System.out.println("restored equals original = "
                + original.equals(recoveredWithZone));

        ZonedDateTime asToronto =
                converted.atZoneSameInstant(torontoZone);
        System.out.println("Toronto same instant = " + asToronto);
        System.out.println("Toronto same offset date-time = "
                + asToronto.toOffsetDateTime().equals(converted));

        OffsetDateTime sameInstantUtc =
                converted.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime sameLocalUtc =
                converted.withOffsetSameLocal(ZoneOffset.UTC);
        System.out.println("UTC same instant = " + sameInstantUtc);
        System.out.println("UTC same local = " + sameLocalUtc);
        System.out.println("UTC local changes instant = "
                + !sameLocalUtc.toInstant().equals(converted.toInstant()));

        ZonedDateTime spring = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, newYorkZone);
        ZonedDateTime zonedNextDay = spring.plusDays(1);
        OffsetDateTime offsetNextDay =
                spring.toOffsetDateTime().plusDays(1);

        System.out.println("spring starting zoned = " + spring);
        System.out.println("zoned +1 calendar day = "
                + zonedNextDay);
        System.out.println("offset +1 calendar day = "
                + offsetNextDay);
        System.out.println("zoned elapsed hours = "
                + Duration.between(
                        spring.toInstant(),
                        zonedNextDay.toInstant()).toHours());
        System.out.println("offset elapsed hours = "
                + Duration.between(
                        spring.toInstant(),
                        offsetNextDay.toInstant()).toHours());
        System.out.println("different destination instants = "
                + !zonedNextDay.toInstant()
                        .equals(offsetNextDay.toInstant()));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac ZonedToOffsetDemo.java
java ZonedToOffsetDemo
```

Expected output when the environment uses 2024 rule data for New York/Toronto:

```text
original = 2024-01-15T09:00-05:00[America/New_York]
converted = 2024-01-15T09:00-05:00
same instant = true
offset retained = true
nano retained = true
rebuilt without region = 2024-01-15T09:00-05:00
rebuilt zone = -05:00
original equals rebuilt = false
restored with explicit zone = 2024-01-15T09:00-05:00[America/New_York]
restored equals original = true
Toronto same instant = 2024-01-15T09:00-05:00[America/Toronto]
Toronto same offset date-time = true
UTC same instant = 2024-01-15T14:00Z
UTC same local = 2024-01-15T09:00Z
UTC local changes instant = true
spring starting zoned = 2024-03-09T12:00-05:00[America/New_York]
zoned +1 calendar day = 2024-03-10T12:00-04:00[America/New_York]
offset +1 calendar day = 2024-03-10T12:00-05:00
zoned elapsed hours = 23
offset elapsed hours = 24
different destination instants = true
```

In the program, `Duration` calculates the distance between **instants**. The line `rebuilt zone = -05:00` proves that `toZonedDateTime()` does not resurrect `America/New_York`. The line `restored equals original = true` succeeds **because the program supplies the original zone from the `newYorkZone` variable**, not because `converted` remembered that zone on its own.

`Instant` is imported in the example without requiring a separate `Instant` variable declaration; the import does not affect compilation or runtime results.

## 8. Conversions Preserving Same Instant vs. Same Local Time

When moving data across zones, state the requirement clearly:

| Intent | API | Preserves instant? | Preserves local time? |
| --- | --- | --- | --- |
| Drop zone, keep offset at the point in time | `zoned.toOffsetDateTime()` | Yes | Yes |
| Drop both zone and offset to keep point in time | `zoned.toInstant()` | Yes | Not stored directly |
| Display `OffsetDateTime` in a new zone | `offset.atZoneSameInstant(zone)` | Yes | Not necessarily |
| Try to keep wall-clock time, attach new zone | `offset.atZoneSimilarLocal(zone)` | Not guaranteed | Tries to keep, may adjust on gap |
| Change offset on `OffsetDateTime`, keep instant | `offset.withOffsetSameInstant(newOffset)` | Yes | Usually not |
| Change offset on `OffsetDateTime`, keep local time | `offset.withOffsetSameLocal(newOffset)` | No, unless offset is unchanged | Yes |
| Turn `OffsetDateTime` into `ZonedDateTime` using offset as zone | `offset.toZonedDateTime()` | Yes | Yes |

**Note:** `OffsetDateTime` also has comparison methods such as `isEqual`, `isBefore`, and `isAfter` based on the instant. Two `OffsetDateTime` instances with different offsets/local times that point to the same instant can return `equals == false` and `isEqual == true`:

```java
OffsetDateTime ny = OffsetDateTime.parse(
        "2024-01-15T09:00-05:00");
OffsetDateTime utc = OffsetDateTime.parse(
        "2024-01-15T14:00Z");

System.out.println(ny.equals(utc));  // false
System.out.println(ny.isEqual(utc)); // true
```

Do not convert objects with different representations to the same time zone just to compare them: use `toInstant()` when the question is "are these the same point in time?".

## 9. Designing Safe Timestamp Storage and Exchange

### Case A — Logs, Past Events, Global Transactions

If you only need **when the event occurred**, `Instant` or an ISO timestamp with an offset is enough to identify the point in time:

```json
{
  "occurredAt": "2024-01-15T14:00:00Z"
}
```

If you need to know what local time the event was recorded in, store `ZoneId` or source metadata as well. `Instant` alone does not store the original zone.

### Case B — Needing to Redisplay in the Exact Original Zone

Store the UTC instant **and** the geographical zone separately:

```json
{
  "occurredAt": "2024-01-15T14:00:00Z",
  "zoneId": "America/New_York"
}
```

You can reconstruct `Instant.parse(occurredAt).atZone(ZoneId.of(zoneId))` to display it in that zone; the result is based on the environment's time-zone rules. If you need to preserve **the exact snapshot of local time/offset that the user saw** at creation time, consider storing those values or the relevant rule version as well, since tzdb data can change.

### Case C — Future Schedules, Recurring Schedules in Local Time

For example, "09:00 every day in New York" cannot be fully represented by a single `OffsetDateTime` or `Instant`. You should store **`LocalTime`, `ZoneId`, and the recurrence rule**, plus any business-specific dates/exceptions:

```json
{
  "localTime": "09:00:00",
  "zoneId": "America/New_York",
  "recurrence": "DAILY"
}
```

When evaluating the schedule for each day:

```java
LocalDate nextDate = LocalDate.of(2024, 3, 10);
LocalTime scheduledTime = LocalTime.of(9, 0);
ZoneId zoneId = ZoneId.of("America/New_York");

ZonedDateTime nextRun = nextDate.atTime(scheduledTime)
        .atZone(zoneId);
Instant triggerInstant = nextRun.toInstant();
```

This is an illustrative snippet; it requires importing `java.time.LocalDate`, `LocalTime`, `ZoneId`, `ZonedDateTime`, and `Instant`.

If the scheduled time falls into a DST gap or overlap, you must define a policy: shift the time, reject it, or pick the earlier/later offset. `ZoneRules.getValidOffsets(localDateTime)` helps detect cases with zero offsets or two offsets.

### Case D — Receiving Only an `OffsetDateTime` from a Partner

If a partner sends:

```text
2024-01-15T09:00:00-05:00
```

You **know the exact instant** of the string, but you **do not know the exact location**. Do not guess the zone by looking at a list of zones that share `-05:00` and picking one arbitrarily. You can display the timestamp with the offset the partner provided, or request an additional `zoneId` field if historical or future scheduling semantics matter.

## 10. Common Pitfalls

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| "`toOffsetDateTime()` loses the UTC time." | Misunderstanding: the instant is preserved. | Verify with `toInstant()`; the zone ID is lost, not the instant. |
| "Keeping `-05:00` means keeping New York." | Multiple zones share the same offset. | Store `ZoneId` separately if zone context matters. |
| "`OffsetDateTime.toZonedDateTime()` recovers the original zone." | The result only uses the offset as the zone. | Use the separately stored original zone ID and `atZoneSameInstant(zone)`. |
| "Adding 1 day on `OffsetDateTime` still follows New York DST." | The offset does not automatically switch `-05:00` ↔ `-04:00`. | Add days on a `ZonedDateTime` that has a region zone ID. |
| "Two zones with the same offset are the same zone." | Loses location identity and date-specific rules. | Distinguish `ZoneId` from `ZoneOffset`. |
| "Attaching a new zone by keeping local time preserves the instant." | `atZoneSimilarLocal` can change the instant. | Use `atZoneSameInstant` if you need to preserve the point in time. |
| "Changing the offset with `withOffsetSameLocal` changes the display time zone." | The instant usually changes. | Use `withOffsetSameInstant` when changing how a time is displayed. |
| "`equals()` is the only way to check for the same instant." | Different offsets can represent the same point in time. | Use `toInstant()` or `isEqual` on the same type. |
| "Having an `Instant` lets you recover the original `ZoneId`." | One instant can be expressed in countless zones. | Store `ZoneId` as separate data. |
| "Time-zone data never changes." | Future schedules can become wrong if laws change. | Manage tzdb updates and schedule recalculation policies. |

## 11. Checklist Before Replacing `ZonedDateTime` with `OffsetDateTime`

1. **Is this value a past event or a future schedule?** If it is a location-bound schedule, you usually need to keep `ZoneId`.
2. **Do you need to recover the original zone?** If so, store a separate `zoneId` field.
3. **Do you need to preserve the instant?** Verify with `source.toInstant().equals(converted.toInstant())`.
4. **Will days/weeks/months/years be added after conversion?** Check DST and zone rules carefully: `OffsetDateTime` does not update its offset automatically.
5. **Are you changing the zone for display?** Use `SameInstant` methods; avoid confusing them with `SameLocal`.
6. **Can historical/future time-zone data change across data versions?** Design to store metadata or recalculate when needed.
7. **Have you tested DST boundaries?** Test spring transitions, autumn transitions, gaps, overlaps, and normal days.

### Self-Check

**1.** What do you get when converting `2024-01-15T09:00-05:00[America/New_York]` to `OffsetDateTime`?  
→ `2024-01-15T09:00-05:00`, retaining the offset, local time, and instant.

**2.** Can you automatically determine `America/New_York` from `2024-01-15T09:00-05:00`?  
→ No. Multiple zones can share the same offset at that point in time.

**3.** What does `offset.toZonedDateTime().getZone()` return if `offset` is `2024-01-15T09:00-05:00`?  
→ `-05:00`, not `America/New_York`.

**4.** Why can `start.toOffsetDateTime().plusDays(1)` differ from `start.plusDays(1)` across DST?  
→ `OffsetDateTime` keeps a fixed offset; `ZonedDateTime` updates the offset according to the zone's rules on the target date.

**5.** You have an `OffsetDateTime` and the original zone ID stored separately; how do you convert while preserving the point in time?  
→ `offset.atZoneSameInstant(ZoneId.of(originalZoneId))`.

**6.** How does `offset.atZoneSameInstant(zone)` differ from `offset.atZoneSimilarLocal(zone)`?  
→ The former preserves the instant; the latter tries to preserve the local date-time and may change the instant.

### Java API References

- [Oracle Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): `toOffsetDateTime()`, `getZone()`, `getOffset()`, `plusDays()`, and DST resolution.
- [Oracle Java SE 17 — `OffsetDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html): `toZonedDateTime()`, `atZoneSameInstant()`, `atZoneSimilarLocal()`, `withOffsetSameInstant()`, `withOffsetSameLocal()`.
- [Oracle Java SE 17 — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): time-zone identifiers and rules.
- [Oracle Java SE 17 — `ZoneRules`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offsets during DST gaps and overlaps.

**Remember:** `ZonedDateTime.toOffsetDateTime()` is a conversion that **preserves the instant but loses time-zone information** if the source has a region zone ID. Use `OffsetDateTime` when a timestamp with an offset is sufficient; if you need local scheduling across DST transitions, **store `ZoneId` separately** or continue using `ZonedDateTime`.
