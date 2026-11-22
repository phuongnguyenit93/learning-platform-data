# Converting LocalDateTime to ZonedDateTime: Requiring ZoneId and DST Policy

## 1. Core Problem

`LocalDateTime` represents a **local date and time**: for example, `2024-11-03T01:30`. It **contains no time zone, no UTC offset, and does not uniquely identify an absolute instant**. To convert it to a `ZonedDateTime`, the application must provide a `ZoneId` and decide how to handle local times that are **missing** or **repeated** when time-zone rules change their offset.

For example, consider the same string `2024-11-03T01:30`:

- In `Asia/Ho_Chi_Minh` on that date, the offset is `+07:00` and the local time identifies a single instant.
- In `America/New_York`, November 3, 2024 is the day DST ends: `01:30` occurs **twice**, once with `-04:00` and once with `-05:00`.
- In `America/New_York` on March 10, 2024, the interval `02:00–02:59:59.999999999` **does not exist** because the clock jumps from `01:59:59` to `03:00`.

Therefore, calling `local.atZone(zone)` always produces a value or throws an exception for out-of-range cases, but it **does not automatically reflect your business policy**. In a DST gap, Java defaults to shifting the time forward; in a DST overlap, Java defaults to preferring the offset before the clock transition, unless a specific API or transition state dictates otherwise. For scheduling, payments, deadlines, or event logs, you must explicitly determine whether those default choices are acceptable.

Lesson objectives:

1. Understand why `LocalDateTime` alone is not enough.
2. Know how to use `ZoneId`, `ZoneRules`, `ZoneOffsetTransition`, and the conversion methods.
3. Distinguish **normal**, **gap**, and **overlap** by the number of valid offsets.
4. Choose an explicit DST policy: reject, adjust the time, or require offset selection.
5. Know how to preserve the absolute instant when changing time zones and write reliable tests.

## 2. Distinguishing Data Types and Meanings

| Java Type | Information Contained | What Is Unknown |
|---|---|---|
| `LocalDateTime` | Year, month, day, hour, minute, second, nanosecond | No offset or zone |
| `ZoneId` | Time-zone region identifier or fixed offset | Not yet attached to a specific time |
| `ZoneOffset` | Offset from UTC, e.g., `-04:00` or `+07:00` | Does not contain a region's history/DST rules |
| `ZonedDateTime` | Local time, `ZoneId`, selected offset | Already identifies an instant |
| `OffsetDateTime` | Local time and specific offset | Does not retain region time-zone rules |
| `Instant` | Absolute point on the timeline | No local time until a zone is chosen |

A region-based `ZoneId`, such as `America/New_York`, uses **time-zone rules (tzdb)** to look up the valid offset for a given date and time. Those rules can include DST as well as other historical or policy changes. `ZoneOffset.ofHours(-5)` only expresses a fixed `-05:00` offset and **does not know when New York transitions DST**.

The following two lines have different meanings:

~~~java
ZoneId region = ZoneId.of("America/New_York");
ZoneOffset fixed = ZoneOffset.ofHours(-5);
~~~

If an application schedules a meeting for "09:00 in New York in July", it must keep the `America/New_York` region so that the rules for July are applied. Using a fixed `-05:00` offset can produce the wrong actual time because New York in summer is typically `-04:00`.

## 3. Basic Conversion When the Local Time Has a Single Valid Instant

The concise approach:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 1, 15, 10, 30);
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime result = local.atZone(zone);
~~~

At the illustrated time, New York has an offset of `-05:00`, so `result` is:

~~~text
2024-01-15T10:30-05:00[America/New_York]
~~~

You can use the equivalent factory when you have a local date-time and a zone:

~~~java
ZonedDateTime result =
        ZonedDateTime.of(local, zone);
~~~

In the normal case, `local.atZone(zone)` or `ZonedDateTime.of(local, zone)` selects the unique valid offset according to `ZoneRules`. When the date-time falls inside a **gap/overlap**, both approaches use Java's default resolution policy.

Without a `ZoneId`, the correct offset cannot be inferred from `LocalDateTime` alone. `ZoneId.systemDefault()` is only appropriate when **the system time zone itself is the business rule**; in services running across multiple machines, containers, or CI, the OS time zone can vary.

### 3.1. How Many Instants Correspond to a Local Time?

With `ZoneRules.getValidOffsets(localDateTime)`:

| Valid Offset Count | State | Meaning |
|---:|---|---|
| 1 | Normal | One local time maps to one instant |
| 0 | Gap | Local time does not exist due to a forward offset change |
| 2 | Overlap | Local time occurs twice due to a backward offset change |

In Java's standard time-zone model, gaps and overlaps are commonly associated with DST transitions; however, offset transitions can also happen due to legal changes or historical time zones, and the transition duration is not necessarily one hour.

You should not merely check `zonedDateTime != null` to conclude that "the input time was valid and preserved." A `LocalDateTime` inside a gap can be **adjusted to a different time** by Java without throwing an exception.

## 4. DST Gap — A Non-Existent Time Interval

In `America/New_York`, on **March 10, 2024**, the clock jumps from right before `02:00` to `03:00` when DST begins. Therefore:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2024, 3, 10, 2, 30);

ZonedDateTime adjusted = missing.atZone(ny);
System.out.println(adjusted);
~~~

Stdout:

~~~text
2024-03-10T03:30-04:00[America/New_York]
~~~

`02:30` did not exist in New York on that day. By default, Java pushes the local time forward by **the gap duration of one hour**, turning it into `03:30` and selecting the new `-04:00` offset. This is convenient in some applications, but it may be wrong if a user scheduled something for "exactly 02:30".

To detect this before converting:

~~~java
ZoneRules rules = ny.getRules();
List<ZoneOffset> validOffsets = rules.getValidOffsets(missing);

System.out.println(validOffsets.size()); // 0
~~~

When a gap occurs, `rules.getTransition(missing)` provides a `ZoneOffsetTransition` with the before/after offsets and the transition duration. For the date above:

~~~java
ZoneOffsetTransition transition = rules.getTransition(missing);
System.out.println(transition.getDuration());      // PT1H
System.out.println(transition.getDateTimeAfter()); // 2024-03-10T03:00
~~~

`getDateTimeAfter()` is **the start of the valid time range after the transition**, whereas the default conversion of `02:30` to `03:30` preserves the minutes within the gap by shifting the entire time forward by one hour. These are **two different policies**:

- "Shift by the gap duration": `02:30 → 03:30`.
- "Move to the first valid time after the gap": `02:30 → 03:00`.

You cannot decide this silently on the user's behalf; depending on whether the application handles reminders, deadlines, or work shifts, the appropriate policy differs.

## 5. DST Overlap — A Time That Occurs Twice

In `America/New_York` on **November 3, 2024**, when DST ends, the clock changes offset from `-04:00` to `-05:00`. The time `01:30` occurs twice:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime first = repeated.atZone(ny);
ZonedDateTime second = first.withLaterOffsetAtOverlap();
~~~

The two results:

~~~text
first  = 2024-11-03T01:30-04:00[America/New_York]
second = 2024-11-03T01:30-05:00[America/New_York]
~~~

By default, `atZone(ny)` selects the **pre-transition offset** during an overlap (`-04:00` in this example). `withLaterOffsetAtOverlap()` selects the **post-transition offset** (`-05:00`). The method names "earlier/later offset" in `withEarlierOffsetAtOverlap()` and `withLaterOffsetAtOverlap()` refer to choosing between the two offsets in an overlap; for New York, the first occurrence happens earlier on the absolute timeline.

The corresponding instants:

~~~text
first.toInstant()  = 2024-11-03T05:30:00Z
second.toInstant() = 2024-11-03T06:30:00Z
~~~

Both represent "01:30 in New York", yet they are **one absolute hour apart**. If you store only the string `2024-11-03T01:30` and the New York zone and later restore it without preserving the offset choice, you may not be able to determine which occurrence the event happened in.

Reading the valid offsets:

~~~java
List<ZoneOffset> offsets =
        ny.getRules().getValidOffsets(repeated);
System.out.println(offsets);
~~~

Stdout:

~~~text
[-04:00, -05:00]
~~~

The returned order is typically the pre-transition offset followed by the post-transition offset. However, business requirements should explicitly state **"first occurrence" or "second occurrence"** or the **specific offset**, rather than expecting users to guess from these two numbers.

## 6. Three Policies to Choose When Converting

A serious application needs to specify how it handles **gaps**, **overlaps**, and **normal times**. Common options:

| State | Policy 1 | Policy 2 | Risk If Left to Silent Defaults |
|---|---|---|---|
| Normal (1 offset) | Select the single valid offset | — | Low ambiguity |
| Gap (0 offsets) | Reject and ask the user to pick another time | Shift by gap duration or to start of valid range | Schedule moves to a time the user did not enter |
| Overlap (2 offsets) | Require choosing "first/second occurrence" | Conventionally pick pre- or post-transition offset | Event may be off by one hour |

For **critical meetings, trading sessions, auditing, or systems requiring exact instants**, a policy that **rejects gaps and requires an offset for overlaps** avoids ambiguity. For display applications or recurring schedules with well-defined rules, you can intentionally choose "shift past the gap" and "pre-transition offset" and document that behavior.

### 6.1. Specific Resolution APIs

- `local.atZone(zone)` / `ZonedDateTime.of(local, zone)`: uses default rules; gaps may be adjusted, and overlaps typically pick the pre-transition offset.
- `ZonedDateTime.ofLocal(local, zone, preferredOffset)`: prefers the offset if it is valid during an overlap; otherwise, falls back to the default rules. **Not a strict API**.
- `ZonedDateTime.ofStrict(local, offset, zone)`: accepts **only when the chosen offset is valid** for the local date-time in the zone; throws `DateTimeException` in a gap or when the offset is invalid.
- `zoned.withEarlierOffsetAtOverlap()` / `withLaterOffsetAtOverlap()`: chooses one of the two offsets when the object is in an overlap. Outside an overlap, they do not change the instant because only one offset is valid.
- `zone.getRules().getValidOffsets(local)`: checks whether there are 0, 1, or 2 offsets so you can enforce your own policy.

**Note:** The word "strict" in `ofStrict` means strictly validating the triple of local time + offset + zone. For an overlap, if you supply **one of the two valid offsets**, `ofStrict` still accepts it; it does not ask the user which occurrence to pick.

### 6.2. Example of Explicit Offset Selection

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime earlier = ZonedDateTime.ofStrict(
        local, ZoneOffset.ofHours(-4), zone);

ZonedDateTime later = ZonedDateTime.ofStrict(
        local, ZoneOffset.ofHours(-5), zone);
~~~

These are two distinct valid values with the same local time and zone, but different instants. If you pass `ZoneOffset.ofHours(-5)` for a date-time in the gap `2024-03-10T02:30`, `ofStrict` throws `DateTimeException` because there is no valid offset for the missing time.

## 7. Standalone Java 17+ Program

Save as **`DstConversionDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstConversionDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime normal =
                LocalDateTime.of(2024, 1, 15, 12, 0);
        System.out.println("Normal offsets: "
                + rules.getValidOffsets(normal));
        System.out.println("Normal: " + normal.atZone(zone));

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 10, 2, 30);
        List<ZoneOffset> gapOffsets = rules.getValidOffsets(gap);
        ZoneOffsetTransition gapTransition = rules.getTransition(gap);

        System.out.println("Gap offsets: " + gapOffsets.size());
        System.out.println("Gap duration: "
                + gapTransition.getDuration());
        System.out.println("Gap default: " + gap.atZone(zone));

        try {
            ZonedDateTime.ofStrict(
                    gap, ZoneOffset.ofHours(-5), zone);
        } catch (DateTimeException ex) {
            System.out.println("Gap strict: rejected");
        }

        LocalDateTime overlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);
        ZonedDateTime earlier = overlap.atZone(zone);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));
        System.out.println("Overlap earlier: " + earlier);
        System.out.println("Overlap later: " + later);
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());

        ZonedDateTime strictLater = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.ofHours(-5), zone);
        System.out.println("Strict later: " + strictLater);
    }
}
~~~

Compile and run commands:

~~~bash
javac DstConversionDemo.java
java DstConversionDemo
~~~

Stdout on a JDK with tzdb rules matching New York in 2024:

~~~text
Normal offsets: [-05:00]
Normal: 2024-01-15T12:00-05:00[America/New_York]
Gap offsets: 0
Gap duration: PT1H
Gap default: 2024-03-10T03:30-04:00[America/New_York]
Gap strict: rejected
Overlap offsets: [-04:00, -05:00]
Overlap earlier: 2024-11-03T01:30-04:00[America/New_York]
Overlap later: 2024-11-03T01:30-05:00[America/New_York]
Earlier instant: 2024-11-03T05:30:00Z
Later instant: 2024-11-03T06:30:00Z
Strict later: 2024-11-03T01:30-05:00[America/New_York]
~~~

The example uses known dates and does not read the current clock. When time-zone rules are updated for another region or a different period, results may change depending on the JDK's time-zone database version. This shows that **time-zone rules are environment-dependent data**, so you should never hardcode an offset for a region across all dates.

## 8. Writing a DST Resolver Following Application Policy

A real-world problem often starts with user input like:

~~~text
localDateTime = 2024-11-03T01:30
zoneId        = America/New_York
preference    = AFTER_TRANSITION
~~~

The application can check before creating the object and reject if information is missing:

~~~java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class StrictDstResolver {
    public static ZonedDateTime resolve(
            LocalDateTime local,
            ZoneId zone,
            boolean chooseLaterOffset) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException(
                    "Local time does not exist in zone: " + local);
        }

        if (offsets.size() > 2) {
            throw new DateTimeException("Unexpected offset count");
        }

        ZoneOffset chosen = offsets.size() == 1
                ? offsets.get(0)
                : offsets.get(chooseLaterOffset ? 1 : 0);

        return ZonedDateTime.ofStrict(local, chosen, zone);
    }
}
~~~

This is a standalone class placed in **`StrictDstResolver.java`**. It **rejects gaps** and selects the pre- or post-transition offset based on the application parameter. In production code, a parameter like `chooseLaterOffset` should only be used when the request source has explicitly determined the choice. If the user has not yet chosen an offset for an overlap, return a state requiring confirmation instead of defaulting to a boolean.

Another policy is shifting the missing time:

~~~java
ZoneOffsetTransition transition =
        zone.getRules().getTransition(local);

if (transition != null && transition.isGap()) {
    LocalDateTime shifted =
            local.plus(transition.getDuration());
    ZonedDateTime adjusted = shifted.atZone(zone);
}
~~~

This is an **illustrative snippet inside a method** where `zone` (`ZoneId`), `local` (`LocalDateTime`), and the appropriate imports are already available. It turns `02:30` in New York on March 10, 2024 into `03:30`. If the requirement is "start at the earliest possible time after the gap", choosing `transition.getDateTimeAfter()` yields `03:00` in this example. These are two different approaches; a clear business decision is required.

### 8.1. Handling Input in a REST API or UI

When a user only provides a local date-time and a zone, an API can return a validation result before saving:

| Case | Appropriate Response |
|---|---|
| Normal | Create `ZonedDateTime` and save or return the instant |
| Gap | Report "time does not exist", suggest the nearest valid time or ask to change the time |
| Overlap | Report that the time has two offsets; ask the user to choose the first/second occurrence |
| Invalid `ZoneId` | Return a validation error; never fall back to the server time zone |

If the product already has a standard rule (for example, "shift gaps by the gap duration, choose the earlier occurrence"), you may not need to prompt the user every time. However, that rule must be documented in the API contract, business specs, and tests; it should not be hidden in the implicit behavior of `atZone`.

## 9. When You Already Have an Instant, Conversion Is Different

If you have an `Instant`, it **already identifies an exact point in time**. To display it in a time zone:

~~~java
Instant instant =
        Instant.parse("2024-11-03T06:30:00Z");
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime zoned = instant.atZone(zone);
// 2024-11-03T01:30-05:00[America/New_York]
~~~

When converting **Instant → ZonedDateTime**, there is generally no DST ambiguity regarding the instant: the zone selects the exact offset for that known point in time. Conversely, **LocalDateTime → ZonedDateTime** must solve the 0/1/2-offset problem.

A less commonly used API:

~~~java
ZonedDateTime zoned = ZonedDateTime.ofInstant(
        local, ZoneOffset.ofHours(-5), zone);
~~~

When you supply `local + offset`, that pair already identifies an instant. `ofInstant(local, offset, zone)` interprets the pair as an instant and then represents it in the target zone; if the offset is invalid for the local time in the target zone, the local time may **change**. Do not treat it as `ofStrict`, because `ofStrict` rejects an invalid triple. When you need to preserve the user's choice and verify that the offset is valid for the zone, use `ofStrict`.

## 10. Changing Zones: Keep the Instant or Keep the Local Time?

Once you have a `ZonedDateTime`, there are two conversion methods that are easy to confuse:

~~~java
ZonedDateTime ny = LocalDateTime
        .of(2024, 11, 3, 1, 30)
        .atZone(ZoneId.of("America/New_York"));

ZonedDateTime sameInstant =
        ny.withZoneSameInstant(ZoneOffset.UTC);

ZonedDateTime sameLocal =
        ny.withZoneSameLocal(ZoneOffset.UTC);
~~~

Results:

~~~text
ny          = 2024-11-03T01:30-04:00[America/New_York]
sameInstant = 2024-11-03T05:30Z
sameLocal   = 2024-11-03T01:30Z
~~~

- `withZoneSameInstant(targetZone)`: **preserves the absolute instant**, changing the date-time view for the target zone. This is the right choice when converting event timestamps.
- `withZoneSameLocal(targetZone)`: tries to keep the corresponding **local wall-clock time**; the instant may change and is still subject to gap/overlap rules in the new zone. Use this only when intentionally reinterpreting a wall-clock time in another zone.

Never use `withZoneSameLocal(ZoneOffset.UTC)` to "convert New York time to UTC" when the goal is to keep the same event: that operation can shift the instant by several hours.

## 11. How DST Affects Adding One Day vs. 24 Hours

Once you have a `ZonedDateTime`, **adding one calendar day** and **adding 24 absolute hours** can produce different results on a DST transition day:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, ny);

ZonedDateTime oneCalendarDay = start.plusDays(1);
ZonedDateTime twentyFourHours = start.plusHours(24);
~~~

For New York when DST starts in 2024:

~~~text
start           = 2024-03-09T12:00-05:00[America/New_York]
oneCalendarDay  = 2024-03-10T12:00-04:00[America/New_York]
twentyFourHours = 2024-03-10T13:00-04:00[America/New_York]
~~~

`plusDays(1)` operates by local calendar day: it keeps 12:00 on the next day and updates the offset, so only **23 absolute hours** elapse. `plusHours(24)` adds a duration of 24 hours, resulting in 13:00 local time the next day.

Choose the addition operation based on the business meaning:

- "Meet at 12:00 every day in New York" → local calendar days and gap/overlap handling rules.
- "Run a job after exactly 24 hours have elapsed" → duration along the instant timeline.

For recurring schedules, each occurrence may need to be checked individually against `ZoneRules`. Do not assume from today's offset that it will remain valid on every future date.

## 12. Storage Design and Round-Tripping

If the goal is to accurately reconstruct an event that already happened, **`Instant`** is the appropriate way to store the absolute point in time; when displaying it, convert to the requested `ZoneId`:

~~~java
Instant occurredAt = zoned.toInstant();
ZonedDateTime view = occurredAt.atZone(displayZone);
~~~

Distinguish between these cases:

1. **An event that already occurred:** store the instant, and optionally store the zone for display conventions.
2. **A future appointment at "09:00 in New York":** store the local date-time, `ZoneId`, and DST policy so the region's rules apply on the execution date. Time-zone rules can change by law, so keep tzdb up to date and define a schedule-update strategy.
3. **A specific chosen time during an overlap:** store the `Instant` or the offset / first-or-second-occurrence choice so the user's decision is not lost. Storing only the local date-time and zone can lose the selected offset information.
4. **Only a fixed offset from the source:** store an `OffsetDateTime` or convert to an instant; an offset does not fully replace a region `ZoneId` for zone-based appointments.

In JSON or a database, avoid storing a local date-time string alone and assuming the backend can infer a unique timestamp. Example payload you can use:

~~~json
{
  "localDateTime": "2024-11-03T01:30:00",
  "zoneId": "America/New_York",
  "preferredOffset": "-05:00"
}
~~~

The backend uses `ofStrict` to ensure the selected offset is actually valid according to tzdb. For a gap, the API should reject it or require special handling; do not equate a provided offset with the local date-time actually existing in the zone.

## 13. Common Pitfalls

1. **Having only a LocalDateTime and assuming you know an Instant:** wrong; it lacks an offset or `ZoneId` and ignores potential DST ambiguity.
2. **Using `ZoneId.systemDefault()` to infer the user's zone:** servers/CI may run in UTC and vary across environments.
3. **Using a fixed `ZoneOffset` instead of a region `ZoneId` for future schedules:** a region's offset can change due to DST or legislation.
4. **Assuming `atZone` preserves the local date-time in a gap:** Java defaults to shifting the missing time forward.
5. **Forgetting that an overlap yields two distinct instants:** the same "01:30" can happen twice, so you must preserve or ask for the offset choice.
6. **Using `ofLocal` with `preferredOffset` and thinking it is a strict check:** the API can fall back, so use `ofStrict` to catch invalid offsets.
7. **Using `ofInstant(local, offset, zone)` to validate the triple:** the API can adjust the local time if the offset does not match the target zone; `ofStrict` is what validates it.
8. **Confusing `withZoneSameLocal` with `withZoneSameInstant`:** the former can change the absolute event time.
9. **Assuming every day is 24 hours:** a local day can be 23, 25, or another number of hours due to offset transitions.
10. **Computing daily schedules by adding 86,400 seconds:** this can shift the local time after DST transitions.
11. **Hardcoding that gaps are always 1 hour and overlaps always have 2 offsets 1 hour apart:** many regions have transitions of other durations; read `ZoneOffsetTransition`.
12. **Assuming every country uses DST:** many regions do not observe DST or have their own transition histories.
13. **Not checking the runtime time-zone database:** tzdb can be updated due to legal changes; test with critical dates and regions.
14. **Storing only local date-time and zone after choosing an offset in an overlap:** if you need to reconstruct the exact event, you must store the instant or the chosen offset.

## 14. Self-Check Questions

**Question 1.** Why does `LocalDateTime.of(2024,11,3,1,30)` not identify a single instant when paired with `America/New_York`?

**Answer:** Because DST ends on that day, causing 01:30 to occur with two offsets, `-04:00` and `-05:00`, corresponding to two instants one hour apart.

**Question 2.** What does `LocalDateTime.of(2024,3,10,2,30).atZone(ZoneId.of("America/New_York"))` return?

**Answer:** `2024-03-10T03:30-04:00[America/New_York]`, because `02:30` falls in a one-hour gap and Java adjusts it forward.

**Question 3.** How do you reject a non-existent local time?

**Answer:** Check `zone.getRules().getValidOffsets(local).isEmpty()` and raise an error, or use `ZonedDateTime.ofStrict(local, offset, zone)` when an offset has been specified.

**Question 4.** How do you select the second occurrence of 01:30 in New York during an overlap?

**Answer:** Choose the `-05:00` offset using `ZonedDateTime.ofStrict(local, ZoneOffset.ofHours(-5), zone)` or call `withLaterOffsetAtOverlap()` on the corresponding overlap value.

**Question 5.** What is the difference between `withZoneSameInstant` and `withZoneSameLocal`?

**Answer:** One preserves the **instant**, while the other tries to keep the **local time**, which can change the instant.

**Question 6.** Why can `plusDays(1)` differ from `plusHours(24)` on a `ZonedDateTime`?

**Answer:** `plusDays` operates on local calendar days, whereas `plusHours` adds elapsed time along the instant timeline; a day with a DST transition may not be exactly 24 hours long.

**Question 7.** When you only want to display a known `Instant` in New York, do you need to manually pick an overlap offset?

**Answer:** No. `instant.atZone(ny)` automatically determines the offset from the instant and the zone's rules; ambiguity only arises when starting from a local date-time without an offset.

**Question 8.** Should you store a single `-05:00` offset for all New York meetings year-round?

**Answer:** No. Use `ZoneId.of("America/New_York")` to apply the region's rules on the specific date and handle gaps/overlaps.

## 15. Practical Rules

- **Input is `LocalDateTime`** → require a `ZoneId`, inspect `ZoneRules`, and choose a policy for normal/gap/overlap before claiming you have an instant.
- **Input is `Instant`** → you can call `instant.atZone(zone)`; there is no ambiguity about the absolute point in time.
- **Gap** → reject, shift by the gap duration, or pick the start of the valid range, depending on business requirements.
- **Overlap** → pick the pre- or post-transition offset or ask the user to confirm; store the choice so it can be reconstructed.
- **Audit/event data** → store `Instant` when you need to identify the exact moment; **region-based schedules** → store the local time, region `ZoneId`, and transition rules.
- **Converting to another zone** → use `withZoneSameInstant` when you want to keep the same event, and only use `withZoneSameLocal` when intentionally reinterpreting the wall-clock time.

`LocalDateTime.atZone(zone)` is very convenient, but system correctness depends on defining and checking your **DST policy** every time a local time is converted into an instant.
