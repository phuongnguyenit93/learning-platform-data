# Skipped Hours During Daylight Saving Time Transition (DST Gap) in `ZonedDateTime`

## 1. The Problem: Why Does a Local Time Not Exist?

When a region begins **Daylight Saving Time (DST)**, clocks may be adjusted **forward**. For example, in `America/New_York` on **2024-03-10**, clocks jumped from **01:59:59 (UTC−05:00)** to **03:00:00 (UTC−04:00)**. According to this region's time zone rules, any local time from `2024-03-10T02:00` up to just before `03:00` **never occurred**.

This invalid local time interval is called a **gap** (skipped interval). It is not a period where the world stops moving: `Instant` values (absolute points on the UTC timeline) remain continuous. Only the local clock display jumps.

| Representation in New York | Corresponding UTC | Notes |
| --- | --- | --- |
| `2024-03-10T01:59:59-05:00` | `2024-03-10T06:59:59Z` | Last second before the clock change |
| `2024-03-10T02:30` | **None** | Local time falls in the gap |
| `2024-03-10T03:00:00-04:00` | `2024-03-10T07:00:00Z` | First valid moment after the clock change |

Do not assume that DST always starts at 02:00, that a gap is always exactly one hour long, or that every country observes DST. The date, time, duration, and even whether a transition happens at all depend on the **`ZoneId` and historical rules** in the Java environment's time zone database (tzdb).

## 2. Distinguishing Three Time Types Before Handling a Gap

- **`LocalDateTime`** holds only a date and clock time (for example, `2024-03-10T02:30`), **without a time zone or UTC offset**. This value can be created successfully even if it does not exist in a specific time zone.
- **`ZoneId`** such as `America/New_York` carries the rule set that determines the UTC offset for each date in the past or future. A `ZoneOffset` such as `-05:00` is only a fixed offset and does not fully describe time zone transitions.
- **`ZonedDateTime`** combines a local date-time, a `ZoneId`, and a valid offset to identify an `Instant`. When constructed from a `LocalDateTime` that falls in a gap, standard factory APIs **adjust the local time forward by the exact duration of the gap**.

Therefore, `LocalDateTime.of(2024, 3, 10, 2, 30)` is structurally valid, but **is not a valid point in time in** `America/New_York` on that day.

## 3. How Does Java Automatically Handle Skipped Hours?

With `LocalDateTime.atZone(zone)` or `ZonedDateTime.of(localDateTime, zone)`, Java applies the following rules:

1. If the local time has **one valid offset**, use that offset.
2. If the local time falls in a **gap** (no valid offset), shift the `LocalDateTime` **forward by the duration of the gap**, then use the offset **after** the transition.
3. If there are **two valid offsets** (an overlap when clocks fall back), that is a different situation from a gap; by default, Java typically chooses the earlier offset if no valid preferred offset is specified.

In New York, `2024-03-10T02:30` is normalized to **`2024-03-10T03:30-04:00[America/New_York]`**. This is the **default API policy**, not necessarily the right policy for every business domain (such as medical appointments, store opening hours, or trading orders).

## 4. Standalone Java 17+ Example: Detecting and Observing a Gap

Save the code below to `DstGapDemo.java`:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstGapDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime requested = LocalDateTime.of(2024, 3, 10, 2, 30);
        ZoneRules rules = zone.getRules();

        List<ZoneOffset> offsets = rules.getValidOffsets(requested);
        ZoneOffsetTransition transition = rules.getTransition(requested);

        System.out.println("Valid offsets: " + offsets);
        System.out.println("Is gap: " + transition.isGap());
        System.out.println("Before: " + transition.getDateTimeBefore()
                + " " + transition.getOffsetBefore());
        System.out.println("After: " + transition.getDateTimeAfter()
                + " " + transition.getOffsetAfter());
        System.out.println("Gap duration: " + transition.getDuration());

        ZonedDateTime adjusted = requested.atZone(zone);
        System.out.println("atZone: " + adjusted);
        System.out.println("Instant: " + adjusted.toInstant());

        try {
            ZonedDateTime.ofStrict(requested, transition.getOffsetBefore(), zone);
            System.out.println("ofStrict: accepted");
        } catch (DateTimeException ex) {
            System.out.println("ofStrict: rejected invalid local time");
        }

        ZonedDateTime fromUtc = ZonedDateTime.ofInstant(
                Instant.parse("2024-03-10T07:30:00Z"), zone);
        System.out.println("From UTC: " + fromUtc);
    }
}
```

Compile and run:

```bash
javac DstGapDemo.java
java DstGapDemo
```

Output (according to tzdb rules for `America/New_York` on 2024-03-10):

```text
Valid offsets: []
Is gap: true
Before: 2024-03-10T02:00 -05:00
After: 2024-03-10T03:00 -04:00
Gap duration: PT1H
atZone: 2024-03-10T03:30-04:00[America/New_York]
Instant: 2024-03-10T07:30:00Z
ofStrict: rejected invalid local time
From UTC: 2024-03-10T03:30-04:00[America/New_York]
```

Key takeaway: `getValidOffsets(requested)` returns an **empty** list because no offset makes `02:30` an actual local time occurring in New York. `atZone` does not throw an error and instead adjusts forward to `03:30`. Conversely, `ofStrict` requires the **local time + offset** pair to be genuinely valid for the `ZoneId`, so it throws a `DateTimeException` on a gap. In the example, the exception is caught so the program finishes running.

## 5. APIs for Detecting and Handling DST Transitions

`ZoneRules` is the main entry point when an application needs **business-level control** before converting a `LocalDateTime` into a `ZonedDateTime`.

| API | Behavior with `LocalDateTime` in a gap |
| --- | --- |
| `zone.getRules().getValidOffsets(local)` | Returns `[]`; size 0 = gap, 1 = normal, 2 = overlap |
| `zone.getRules().getTransition(local)` | Returns a `ZoneOffsetTransition` with transition details; check `isGap()` |
| `transition.getDuration()` | The amount the clock jumps forward, such as `PT1H` |
| `transition.getDateTimeBefore()` / `getDateTimeAfter()` | The two clock times at the transition boundary (here, `02:00` and `03:00`) |
| `local.atZone(zone)` | Automatically shifts the local time in a gap forward |
| `ZonedDateTime.ofStrict(local, offset, zone)` | Throws `DateTimeException` if the offset is not valid for that local date-time |
| `ZonedDateTime.ofInstant(instant, zone)` | Converts a known UTC instant to the time zone; never produces a non-existent local time |

A general check before creating a schedule:

```java
// Illustrative snippet using existing LocalDateTime local and ZoneId zone variables.
List<ZoneOffset> validOffsets = zone.getRules().getValidOffsets(local);
if (validOffsets.isEmpty()) {
    // Gap: prompt the user or apply the documented scheduling policy.
} else if (validOffsets.size() == 2) {
    // Overlap: need to distinguish between the earlier/later occurrence of the same local time.
} else {
    // The local time uniquely determines a single offset.
}
```

To avoid confusion: `getTransition(local)` normally returns `null` if the time does not fall within a transition. Check `transition != null && transition.isGap()` before using it in general-purpose code. The standalone example above intentionally chose a time **known to be inside a gap**.

## 6. Choosing a Business Policy Before Persisting a Schedule

Java shifts `02:30` to `03:30` by default; the business domain must explicitly decide whether this is desired. Common reasonable policies include:

| Policy | For a 02:30 request in a 02:00–03:00 gap | Use case |
| --- | --- | --- |
| **Reject / ask user to pick again** | Report “02:30 does not exist in the selected region/date” | Ticket booking, payments, appointments requiring confirmation |
| **Shift by gap duration** | Set to 03:30 | Wanting to preserve minutes past the hour and accepting rescheduling |
| **Move to the first valid time** | Set to 03:00 | Running a task as soon as possible after the gap |
| **Skip that day's run** | Do not trigger that run | Recurring schedules with a rule to skip invalid occurrences |

Once a gap is confirmed, to get the **first valid local time**, you can use `transition.getDateTimeAfter().atZone(zone)`. This differs from `local.atZone(zone)`: an input of `02:30` produces **03:00** under the “first valid” policy, whereas it produces **03:30** under the “shift by full gap” policy.

Example of a method that rejects non-existent times:

```java
// Illustrative snippet; place inside a class and import java.time.*.
static ZonedDateTime rejectDstGap(LocalDateTime local, ZoneId zone) {
    if (zone.getRules().getValidOffsets(local).isEmpty()) {
        throw new IllegalArgumentException(
                "Thoi diem dia phuong khong ton tai trong mui gio da chon");
    }
    return local.atZone(zone);
}
```

This method only handles **gaps**; if the business logic needs to distinguish between the two occurrences of the same clock time during an **overlap**, you must also handle the `getValidOffsets(local).size() == 2` case.

## 7. Adding Time Across a Gap: Elapsed Duration vs. Wall-Clock Time Differ

Suppose in New York you start at `2024-03-10T01:30-05:00`. Across the DST transition:

- **Adding 1 hour on the timeline** (`zoned.plusHours(1)`) lands at **03:30-04:00**; exactly 60 minutes of real time have elapsed, even though the clock display increased by two hours.
- **Adding 1 hour to `LocalDateTime`** (`local.plusHours(1)`) gives **02:30**, which **does not exist** in New York; attaching `ZoneId` afterward pushes it to **03:30**.
- **`Duration.between(start, end)`** on two `ZonedDateTime` instances reflects the distance on the real timeline. In the example from 01:30-05:00 to 03:30-04:00, the result is **`PT1H`**, not two hours.

Even though one example may yield the same final result, **addition rules on `Instant`, `LocalDateTime`, and calendar days** differ; do not assume general equivalence. In particular, `plusDays(1)` on `ZonedDateTime` follows **local days** and can produce an actual elapsed duration of 23 or 25 hours near DST, whereas `plusHours(24)` is always 24 hours on the timeline.

A schedule like “every day at 02:30 New York time” therefore cannot be implemented accurately by repeatedly adding `Duration.ofHours(24)` to an `Instant`: the local time will drift when offset rules change. Instead, store **`LocalTime` + `ZoneId` + gap/overlap policy**, and recalculate for each day.

## 8. Converting Time Zones for the Right Purpose

Two `ZonedDateTime` APIs are very easy to confuse:

- **`withZoneSameInstant(otherZone)`** keeps the UTC instant unchanged, so the local clock time changes according to the target time zone; suitable for displaying an already-fixed event.
- **`withZoneSameLocal(otherZone)`** tries to keep the clock date and time unchanged; if that time falls in a gap in the target time zone, Java may adjust it forward. The UTC instant therefore often changes; suitable only when you intentionally reinterpret a local wall-clock time in a new region.

Do not edit time strings by replacing `-05:00` with `-04:00` or using a fixed offset for the entire year. Doing so can alter the actual point in time and ignore the transition history of `ZoneId`.

## 9. Data Storage and System Design

1. **User-entered appointments:** accept `LocalDate`, `LocalTime`, and an IANA `ZoneId`; check valid offsets **before** finalizing the instant. Document the policy if a gap is encountered, and do not silently shift the time in domains that require exact clock times.
2. **Events that already occurred:** store an `Instant`/UTC timestamp for comparison, and also store `ZoneId` if you need to reconstruct the local-time context. Storing only `LocalDateTime` risks losing time zone information and fails to identify a unique UTC instant.
3. **Recurring jobs:** store the rule in terms of local time, `ZoneId`, and gap/overlap handling; on each run, compute the `Instant` for the target date using `ZoneRules`.
4. **Testing:** use DST transition dates with known rules (such as `2024-03-10` for New York), and avoid `ZoneId.systemDefault()` or `LocalDateTime.now()` in deterministic test cases.
5. **Operations:** time zone rules provided by tzdb can be updated due to legislative changes. Keep the JDK/tzdb up to date and re-verify long-term schedules; never assume all regions change clocks on the same date.

## 10. Common Pitfalls and How to Avoid Them

- **Confusing a syntactically valid `LocalDateTime` with a real local point in time.** Always check `ZoneRules.getValidOffsets(local)` when the input is a user's wall-clock time and the application requires validity checks.
- **Assuming `atZone` throws an error on a gap.** This API normally **adjusts forward automatically**; use `getValidOffsets` or `ofStrict` when you want to detect or reject a gap.
- **Using a fixed `ZoneOffset` instead of `ZoneId`.** An offset does not store DST rules; a time like `02:30-05:00` can be a valid UTC instant as an `OffsetDateTime` yet **not** a valid local time in New York on 2024-03-10.
- **Using `plusHours(24)` for daily scheduling.** It preserves 24 elapsed hours, not the same wall-clock time each day.
- **Confusing a gap with an overlap.** A gap has **0 valid offsets** (the time never occurs); an overlap has **2 valid offsets** (the time occurs twice). The two situations require different policies.
- **Ignoring tzdb updates.** DST rules are region- and era-specific; accurate historical examples must be based on a specific zone and date.

## 11. Self-Check Questions

**Scenario A.** A user selects `2024-03-10 02:45` in New York. What does `LocalDateTime.atZone(ZoneId.of("America/New_York"))` return?

**Answer:** `2024-03-10T03:45-04:00[America/New_York]`. The time 02:45 falls inside a one-hour gap, so Java shifts it to 03:45.

**Scenario B.** `ZoneRules.getValidOffsets(...)` returns `[]`. Can you work around this by manually picking `-05:00` and calling `ofStrict`?

**Answer:** No. There is no valid offset for **that local time in that `ZoneId`**. `ofStrict` rejects it; the application must apply a policy for the skipped hour.

**Scenario C.** An event is recorded as an `Instant`. When converted to `America/New_York`, could the result be `2024-03-10T02:30` on the DST transition day mentioned above?

**Answer:** No. Every `Instant` maps to a valid local time according to the region's rules; `02:30` on that date does not exist in New York.

**Remember:** With `ZonedDateTime`, a gap occurs when **local clocks jump forward**. A `LocalDateTime` in a gap has 0 valid offsets, `atZone` normally pushes it forward, and business applications must actively decide whether to **reject, reschedule, or skip the run**.
