# How atZone() Handles Gaps and Overlaps by Default

`LocalDateTime` only stores the year, month, day, hour, minute, second, and nanosecond; it **does not contain a UTC offset or a time zone name**. When calling `localDateTime.atZone(zone)`, Java uses the zone's rules (`ZoneRules`) to create a `ZonedDateTime`. This operation is usually straightforward, but in places with clock changes such as *daylight saving time* (DST), a local time may **not exist** (*gap*) or may **occur twice** (*overlap*).

Here are the three most important default rules:

1. **Normal time:** there is one valid offset, so Java keeps the local date and time unchanged and selects that offset.
2. **Gap:** there is no valid offset; Java **shifts the local time forward by the length of the gap** and uses the offset after the transition.
3. **Overlap:** there are two valid offsets; Java **keeps the local date and time unchanged** and prefers the **offset before the transition** (*earlier offset*, usually the summer/DST offset).

This means `atZone()` **does not always just "attach a time zone"**: it can alter the requested time, or it has to pick one of two instants. You need to understand that rule before saving schedules, converting to an `Instant`, or computing an epoch timestamp.

## 1. Time Types Involved in the Conversion

| Java Type | What It Contains | Meaning in This Lesson |
|---|---|---|
| `LocalDateTime` | Local date and time, without an offset. | Input, potentially ambiguous. |
| `ZoneId` | Zone identity with historical/future rules, e.g., `America/New_York`. | Provides offset rules at the date and time under consideration. |
| `ZoneOffset` | Offset from UTC, e.g., `-04:00`, `-05:00`. | A specific offset choice. |
| `ZoneRules` | Rules and offset transitions of the zone. | Checks for normal time, gap, or overlap. |
| `ZonedDateTime` | Local time, `ZoneId`, and resolved offset. | Result of `atZone()`. |
| `Instant` | Absolute point in time, independent of regional display. | Actual event timestamp after conversion. |

Example:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 5, 10, 10, 15);
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime resolved = local.atZone(zone);
Instant instant = resolved.toInstant();
~~~

The snippet above is **illustrative code** that requires importing the `java.time` types and placing it inside a method. May 10, 2024 in New York is a normal time with offset `-04:00`, so `resolved` corresponds to `2024-05-10T10:15-04:00[America/New_York]`.

**`ZoneId` is not synonymous with `ZoneOffset`.** A zone can use offset `-05:00` in winter and `-04:00` in summer. If you only use `ZoneOffset.ofHours(-5)` for the entire year, you are ignoring DST rules.

## 2. Rules for Looking Up Valid Offsets

Java lets you directly inspect all offsets that match a `LocalDateTime`:

~~~java
List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
~~~

This is illustrative code; it requires importing `java.time.ZoneOffset` and `java.util.List`, as well as declaring `zone` and `local`.

| `getValidOffsets(local)` | Case | What will `local.atZone(zone)` do? |
|---|---|---|
| List of **1** element | Normal time | Keeps the local time and applies the single offset. |
| **Empty** list | Gap | Shifts the time forward by the gap duration, selects the post-transition offset. |
| List of **2** elements | Overlap | Keeps the local time, prefers the pre-transition offset. |

`ZoneRules.getTransition(local)` can return a `ZoneOffsetTransition` when the local time falls in a gap or overlap. From there, you can inspect the before/after offsets, transition duration, and whether it is a gap or overlap. For a normal date and time, `getTransition(local)` usually returns `null`; do not call methods on the result without checking.

Both of the following examples use `America/New_York` in **2024**. That is specific historical data; there is no universal rule that "every zone in the world transitions at 02:00 and by exactly one hour."

## 3. Gap: Nonexistent Time Is Pushed Forward to a Valid Time

New York started DST on **2024-03-10**. The clock jumped from `01:59:59-05:00` to `03:00:00-04:00`:

~~~text
2024-03-10 (America/New_York)

01:59:59 -05:00
        ↓ one real second
03:00:00 -04:00

02:00:00 to 02:59:59.999... do not occur.
~~~

Therefore, `2024-03-10T02:30` is a structurally valid `LocalDateTime` value, but **not a civil time that ever existed** in New York on that day.

~~~java
LocalDateTime requested = LocalDateTime.of(2024, 3, 10, 2, 30);
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime resolved = requested.atZone(newYork);
~~~

This is illustrative code. The value of `resolved` is:

~~~text
2024-03-10T03:30-04:00[America/New_York]
~~~

Java pushes 02:30 forward by **one hour** to 03:30 because the gap in this example is one hour long. The corresponding `Instant` is `2024-03-10T07:30:00Z`.

Key points:

- `atZone()` **does not automatically throw an exception** when the local time falls in a gap.
- The local time inside the **result** has changed from 02:30 to 03:30.
- The original `requested` variable is unchanged because `LocalDateTime` is immutable.
- No instant exists for the exact label "02:30 in New York" on that day according to the zone rules.

A gap can be 30 minutes, one hour, or another duration depending on a zone's history. Java shifts **by the transition duration** rather than hardcoding a one-hour addition.

For scheduling, an application must decide whether to accept this default adjustment or reject the user-entered time. An appointment for "02:30 sharp" might need to report an error instead of silently moving to 03:30.

## 4. Overlap: One Local Time Corresponds to Two Instants

On **2024-11-03**, New York ended DST. The clock moved back from `01:59:59-04:00` to `01:00:00-05:00`:

~~~text
2024-11-03 (America/New_York)

01:00–01:59  -04:00  (first occurrence)
      ↓ clock moves back
01:00–01:59  -05:00  (second occurrence)
~~~

Thus, the local time `2024-11-03T01:30` has **two valid offsets**:

| Local time | Offset | Instant |
|---|---|---|
| `2024-11-03T01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `2024-11-03T01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

The two instants are **3600 seconds** apart, yet the local hour and minute label is identical.

When calling:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime first = local.atZone(newYork);
ZonedDateTime second = first.withLaterOffsetAtOverlap();
~~~

This is illustrative code. `atZone()` defaults to selecting the pre-transition offset `-04:00`. `withLaterOffsetAtOverlap()` selects the post-transition offset `-05:00`.

Note: the term *earlier offset* in the Javadoc refers to the **order before/after the transition**, not a numerically smaller offset value. In this example, `-04:00` is numerically greater than `-05:00`. Do not sort offsets as strings or numbers and assume the smallest element is the first occurrence.

If a user actually chose the second 01:30, code that calls default `atZone()` will produce an **instant that is off by one hour** unless the application records and applies the specific choice.

## 5. Java 17+ Example: Observing Default Behavior Directly

Save `AtZoneDefaultsDemo.java`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class AtZoneDefaultsDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime normal = LocalDateTime.of(2024, 5, 10, 10, 15);
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        ZonedDateTime normalValue = normal.atZone(zone);
        ZonedDateTime gapValue = gap.atZone(zone);
        ZonedDateTime first = overlap.atZone(zone);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();

        System.out.println("Normal: " + normalValue);
        System.out.println("Gap requested: " + gap);
        System.out.println("Gap resolved: " + gapValue);
        System.out.println("Gap instant: " + gapValue.toInstant());
        System.out.println("Overlap default: " + first);
        System.out.println("Overlap later: " + second);
        System.out.println("First instant: " + first.toInstant());
        System.out.println("Second instant: " + second.toInstant());
        System.out.println("Same instant? "
                + first.toInstant().equals(second.toInstant()));
    }
}
~~~

Compile and run:

~~~bash
javac AtZoneDefaultsDemo.java
java AtZoneDefaultsDemo
~~~

Stdout (with 2024 New York zone data):

~~~text
Normal: 2024-05-10T10:15-04:00[America/New_York]
Gap requested: 2024-03-10T02:30
Gap resolved: 2024-03-10T03:30-04:00[America/New_York]
Gap instant: 2024-03-10T07:30:00Z
Overlap default: 2024-11-03T01:30-04:00[America/New_York]
Overlap later: 2024-11-03T01:30-05:00[America/New_York]
First instant: 2024-11-03T05:30:00Z
Second instant: 2024-11-03T06:30:00Z
Same instant? false
~~~

**Reading the output:**

- The `Normal` line keeps the local time 10:15 and adds the single offset.
- `Gap requested` is an invalid input according to zone rules, but `Gap resolved` was shifted by Java to 03:30.
- `Overlap default` and `Overlap later` both keep 01:30, have different offsets, and therefore different `Instant` values.

In real systems, check **both the offset and the instant**, rather than only comparing the year/month/day/hour/minute fields of `ZonedDateTime`.

## 6. Inspecting ZoneRules and ZoneOffsetTransition

`ZoneRules` helps detect cases that require custom policies. `ZoneOffsetTransition` tells you the transition duration (positive for a gap, negative for an overlap) and the offsets on both sides.

File `InspectTransitionsDemo.java`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;

public class InspectTransitionsDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime normal = LocalDateTime.of(2024, 5, 10, 10, 15);
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        ZoneOffsetTransition gapTransition = rules.getTransition(gap);
        ZoneOffsetTransition overlapTransition =
                rules.getTransition(overlap);

        System.out.println("Normal offsets: "
                + rules.getValidOffsets(normal));
        System.out.println("Gap offsets: "
                + rules.getValidOffsets(gap));
        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));
        System.out.println("Gap? " + gapTransition.isGap());
        System.out.println("Gap duration: "
                + gapTransition.getDuration());
        System.out.println("Overlap? "
                + overlapTransition.isOverlap());
        System.out.println("Overlap duration: "
                + overlapTransition.getDuration());
    }
}
~~~

Run:

~~~bash
javac InspectTransitionsDemo.java
java InspectTransitionsDemo
~~~

Stdout:

~~~text
Normal offsets: [-04:00]
Gap offsets: []
Overlap offsets: [-04:00, -05:00]
Gap? true
Gap duration: PT1H
Overlap? true
Overlap duration: PT-1H
~~~

In this demo program, `getTransition()` returns data because both `gap` and `overlap` fall within a known transition. For a normal local time, `getTransition(local)` can return `null`; always check before calling `isGap()` or `getDuration()`.

When processing user-entered schedules:

1. Use `zone.getRules().getValidOffsets(local)`.
2. If there are **0 offsets**, ask the user to re-enter or apply a documented time-shifting policy.
3. If there is **1 offset**, you can create the corresponding `ZonedDateTime`.
4. If there are **2 offsets**, ask the user to choose an offset or apply a consistent rule for the first/second occurrence.
5. Record the decision for auditing and accurate conversion to `Instant`.

## 7. Rejecting Automatic Adjustment or Selection: ZonedDateTime.ofStrict()

If business requirements dictate that the local time and offset must be strictly valid exactly as chosen by the user, use:

~~~java
ZonedDateTime.ofStrict(local, selectedOffset, zone);
~~~

This is illustrative code requiring `local`, `selectedOffset`, and `zone` to be declared.

How `ofStrict()` differs from `atZone()`:

- Gap: no valid offset → **throws `DateTimeException`**, does not shift the time.
- Normal time: accepts only the single valid offset.
- Overlap: accepts either of the two offsets if explicitly specified.
- Offset does not match the `ZoneId`/date-time → throws an exception.

The file `StrictResolutionDemo.java` shows how to require the user to choose an offset during an overlap:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictResolutionDemo {
    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, ZoneOffset chosen) {

        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException("Nonexistent local time");
        }
        if (valid.size() == 2 && chosen == null) {
            throw new IllegalArgumentException("Ambiguous local time");
        }

        ZoneOffset offset =
                chosen == null ? valid.get(0) : chosen;

        if (!valid.contains(offset)) {
            throw new IllegalArgumentException("Invalid offset");
        }
        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        try {
            resolve(gap, zone, null);
        } catch (IllegalArgumentException e) {
            System.out.println("Gap rejected: " + e.getMessage());
        }

        try {
            resolve(overlap, zone, null);
        } catch (IllegalArgumentException e) {
            System.out.println("Overlap rejected: " + e.getMessage());
        }

        ZonedDateTime earlier =
                resolve(overlap, zone, ZoneOffset.ofHours(-4));
        ZonedDateTime later =
                resolve(overlap, zone, ZoneOffset.ofHours(-5));

        System.out.println("Earlier instant: "
                + earlier.toInstant());
        System.out.println("Later instant: "
                + later.toInstant());
    }
}
~~~

Run:

~~~bash
javac StrictResolutionDemo.java
java StrictResolutionDemo
~~~

Stdout:

~~~text
Gap rejected: Nonexistent local time
Overlap rejected: Ambiguous local time
Earlier instant: 2024-11-03T05:30:00Z
Later instant: 2024-11-03T06:30:00Z
~~~

This is **an illustrative policy**, not a mandatory requirement for every application. For example, a scheduler might automatically shift to a valid time, whereas room bookings or sensitive transaction timestamps might need to reject ambiguous/nonexistent input to preserve user intent.

## 8. Similarly Named APIs with Different Behaviors

### LocalDateTime.atZone(zone) and ZonedDateTime.of(local, zone)

`LocalDateTime.atZone(zone)` and `ZonedDateTime.of(local, zone)` use the **same default resolution rules**: shifting forward across a gap and preferring the pre-transition offset in an overlap.

### ZonedDateTime.ofLocal(local, zone, preferredOffset)

`ZonedDateTime.ofLocal(local, zone, preferredOffset)` takes a **preferred** offset. If that offset is valid during an overlap, Java uses it. If it is not valid, the method can fall back to the default rules. During a gap, it still adjusts the local time. Therefore, `ofLocal` **is not strict validation**.

### LocalDateTime.atOffset(offset)

`local.atOffset(offset)` creates an `OffsetDateTime` with a fixed offset, **without consulting the zone's `ZoneRules`**. It can create `2024-03-10T02:30-05:00` even though 02:30 did not exist on New York clocks that day. If the intent is "New York time," simply attaching `-05:00` is not enough for validation.

### withEarlierOffsetAtOverlap() and withLaterOffsetAtOverlap()

These two methods are used on `ZonedDateTime` to select the pre-transition or post-transition offset when in an overlap. If the time is not in an overlap, they do not force an invalid offset change. They are very useful when a user confirms the "first occurrence" or "second occurrence."

### withZoneSameInstant() and withZoneSameLocal()

- `withZoneSameInstant(otherZone)` changes the display zone while keeping the **same `Instant`**.
- `withZoneSameLocal(otherZone)` tries to keep the local date and time and then resolves it using the new zone's rules, so the **`Instant` may change**.

To convert UTC logs to Vietnam time for display, use `instant.atZone(zone)` or `withZoneSameInstant`; do not use `withZoneSameLocal` when you need to preserve the exact event timestamp.

### Operations on an Existing ZonedDateTime

When performing operations on a `ZonedDateTime` that already has an offset, some operations that modify the local date/time may **prefer keeping the current offset if it remains valid** in the overlap region. This is a different context from `LocalDateTime.atZone(zone)`, which creates a new value from an input without an offset. Therefore, you should not generalize that every operation on `ZonedDateTime` re-selects the pre-transition offset in the same way.

## 9. Scheduling Example and Stored Data

A user schedules `2024-11-03T01:30` in New York. If they select the **second occurrence**, you can store the interpreted data:

~~~json
{
  "requestedLocalDateTime": "2024-11-03T01:30:00",
  "zoneId": "America/New_York",
  "selectedOffset": "-05:00",
  "resolvedInstant": "2024-11-03T06:30:00Z"
}
~~~

Also store the `ZoneId` when the goal is a zone-based schedule; the offset chosen for one run does not mean all future runs will use that same offset.

If a user enters `2024-03-10T02:30` in New York, you can apply a rejection policy or shift by the gap. With a shifting policy, the audit information might look like this:

~~~json
{
  "requestedLocalDateTime": "2024-03-10T02:30:00",
  "zoneId": "America/New_York",
  "resolutionPolicy": "SHIFT_FORWARD_BY_GAP",
  "resolvedLocalDateTime": "2024-03-10T03:30:00",
  "resolvedInstant": "2024-03-10T07:30:00Z"
}
~~~

These two JSON snippets are **illustrative data models**, not output automatically generated by a Java API. Keeping the requested local time helps explain why the resolved result differs from the entered time.

For events that have already happened, if you already know the `Instant`, you can convert it via `instant.atZone(zone)` for display without having to choose between two instants: the source instant is uniquely determined. Ambiguity happens when going in the direction **local time without offset → instant**.

**You cannot reliably recover the instant from legacy data containing only the string `"2024-11-03 01:30"`** without knowing the zone, offset, or rule that was applied. When migrating data, you need a well-founded convention from the source and should flag ambiguous records.

### Recurring Schedules Across Multiple Years

A schedule for "01:30 every day in New York" must be evaluated against `ZoneRules` on the **date of each occurrence**. Using a fixed offset for the entire schedule will be wrong after a DST transition. Your policy should clearly specify:

- If that day's time does not exist: skip the occurrence, shift the time, or notify the user?
- If that time repeats: run on the first occurrence, the second occurrence, or both?
- If national time zone rules change: how to update TZDB and re-evaluate future schedules?

For multi-zone processing, avoid using `ZoneId.systemDefault()` unless the system clock truly represents the business zone. Pass an explicit `ZoneId` from the request or configuration.

## 10. Common Mistakes

| Mistake | Why It Is Wrong | How to Handle It |
|---|---|---|
| "`atZone()` only attaches the zone without changing local time." | In a gap, the time is shifted forward. | Check `getValidOffsets` and compare input/output. |
| "A time in a gap automatically throws an exception." | `atZone` adjusts by default instead of rejecting. | Check beforehand or use `ofStrict`. |
| "In an overlap, there is only one UTC timestamp." | There are two offsets and two instants. | Store/select the offset according to policy. |
| "Earlier offset means the numerically smaller offset." | Pre/post-transition order differs from numerical order. | Use `ZoneRules` and `withEarlier/LaterOffsetAtOverlap`. |
| "New York is always -05:00." | DST changes it to -04:00 in summer. | Use `ZoneId` with the rules for that date. |
| "`atOffset` also checks New York's DST." | It only attaches a fixed offset. | Use `ZoneId`/`ZoneRules` to validate. |
| "`ofLocal` enforces a valid `preferredOffset`." | It can fall back to the default. | Use `ofStrict` when strict validation is needed. |
| "`withZoneSameLocal` preserves the `Instant`." | It can change the point in time. | Use `withZoneSameInstant`. |
| "All DST zones shift by exactly one hour." | Historical and local transitions can have different durations. | Check `ZoneOffsetTransition.getDuration()`. |
| "The server's time is enough to know the user's zone." | The server may be in a different zone. | Store the `ZoneId` of the business context. |

## 11. Self-Check Questions

**1.** What does calling `LocalDateTime.of(2024, 3, 10, 2, 30).atZone(ZoneId.of("America/New_York"))` return?

**Answer:** `2024-03-10T03:30-04:00[America/New_York]`. The one-hour gap causes the local time to be shifted forward by one hour.

**2.** Why does `2024-11-03T01:30` in New York have two instants?

**Answer:** Because the clock moves back from `-04:00` to `-05:00`; the two results are `2024-11-03T05:30:00Z` and `2024-11-03T06:30:00Z`.

**3.** Which occurrence does `atZone` choose when encountering this overlap?

**Answer:** By default, it prefers the pre-transition offset, `-04:00`, corresponding to the first occurrence. Use `withLaterOffsetAtOverlap()` for the second occurrence.

**4.** How many elements does `getValidOffsets(local)` have if the local time falls in a gap?

**Answer:** 0, because no offset makes that local time valid in the zone.

**5.** If you want to require the user to provide a truly valid offset and reject gaps, which API should you use?

**Answer:** Check `ZoneRules.getValidOffsets` first, then create it with `ZonedDateTime.ofStrict(local, chosenOffset, zone)`.

**6.** If you already have an `Instant` for an event, does converting it to a new zone change the event timestamp?

**Answer:** No. `instant.atZone(zone)` displays the same instant in the zone's local time; it does not create another instant. Gap/overlap ambiguity applies to the direction from a local time without an offset to an instant.

## Key Takeaways

**`LocalDateTime.atZone(zone)` resolves zone rules rather than just adding a time zone label.** It **keeps the local time if normal**, **shifts forward by the gap duration**, and **prefers the pre-transition offset in an overlap**. When default behavior does not meet business requirements, detect it using `ZoneRules.getValidOffsets` and enforce an explicit policy, optionally using `ZonedDateTime.ofStrict` to control the offset. Clearly distinguish between the **user-requested local time**, the **selected offset**, and the **final `Instant`**.
