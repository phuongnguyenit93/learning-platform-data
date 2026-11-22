# Validating Date-Time, Offset, and Time Zone Combinations with ZonedDateTime.ofStrict()

## 1. Why Is Strict Validation Needed?

A `LocalDateTime` describes a local date and time (for example, `2026-11-01T01:30`), without containing a time zone or offset. A `ZoneId` such as `America/New_York` specifies a region and its time transition rules; a `ZoneOffset` such as `-05:00` specifies a concrete UTC offset. To turn a local date-time into an absolute point in time, the combination of information must **comply with the time zone rules at that exact date and time**.

For example, New York typically has an offset of `-05:00` in winter and `-04:00` in summer. On 2026-07-01, an appointment at 09:30 in New York corresponds to `2026-07-01T13:30:00Z` because the valid offset is `-04:00`. If a client sends 09:30, `-05:00`, and `America/New_York`, computing `toInstant(-05:00)` still yields a mathematically valid timestamp, but it **is no longer 09:30 in New York**.

To prevent inconsistent combinations, Java provides:

```java
ZonedDateTime.ofStrict(
    LocalDateTime localDateTime,
    ZoneOffset offset,
    ZoneId zone
);
```

This is **illustrative syntax**, not a standalone compilable call: the type names represent the parameters. When given valid values, `ofStrict()` returns a `ZonedDateTime`; when `offset` is invalid for `localDateTime` in `zone`, it throws `DateTimeException`. It **does not automatically adjust the time** during a DST gap and **does not automatically choose an offset** during a DST overlap.

This lesson focuses on the meaning of `ofStrict`, how to retrieve valid offsets, how it compares to APIs with automatic time-resolution policies, and how to apply it in scheduling systems.

## 2. Related Date-Time Types

| Type | Meaning | Example | Sufficient to Determine an Instant? |
| --- | --- | --- | --- |
| `LocalDateTime` | Local date and time, without offset/zone | `2026-07-01T09:30` | No |
| `ZoneOffset` | Fixed UTC offset at a point in time | `-04:00`, `+07:00` | Requires LocalDateTime |
| `ZoneId` | Region identity and offset/DST rules | `America/New_York` | Requires an instant or a date-time and resolution policy |
| `OffsetDateTime` | LocalDateTime + ZoneOffset | `2026-07-01T09:30-04:00` | Yes |
| `ZonedDateTime` | Local date-time + zone ID + resolved offset | `2026-07-01T09:30-04:00[America/New_York]` | Yes |
| `Instant` | Absolute point on the UTC timeline | `2026-07-01T13:30:00Z` | It is the absolute timestamp itself |

A region `ZoneId` contains time zone rules provided by the JDK's tzdb. `ZoneOffset` is a subclass of `ZoneId`, but a fixed offset such as `-05:00` does **not** indicate that New York uses `-04:00` in summer. You should not treat the current offset as the rule for all dates.

### Three Outcomes from a LocalDateTime and ZoneId

Due to Daylight Saving Time (DST), a wall-clock date-time in a region can have:

- **One valid offset:** a normal point in time, mapping to a single `Instant`.
- **No valid offset (gap):** the local clock jumps forward; the time entered by the user **never occurs**.
- **Two valid offsets (overlap):** the clock falls back; the same time entered by the user occurs **twice**, each corresponding to a different `Instant`.

In New York in 2026:

| Local Date-Time | Status | Valid Offset |
| --- | --- | --- |
| `2026-07-01T09:30` | Normal, summer | `-04:00` |
| `2026-12-01T09:30` | Normal, winter | `-05:00` |
| `2026-03-08T02:30` | DST gap | None |
| `2026-11-01T01:30` | DST overlap | `-04:00` and `-05:00` |

Precisely at a gap or overlap, "combining a date-time with a zone" either has no unique answer or no valid answer at all. `ofStrict()` forces the caller to supply a specific offset and validates that offset.

## 3. Signature, Parameters, and Behavior of ofStrict()

Java SE 17 API:

```java
public static ZonedDateTime ofStrict(
    LocalDateTime localDateTime,
    ZoneOffset offset,
    ZoneId zone
)
```

The snippet above is an **illustrative signature declaration**, not a standalone runnable class.

- `localDateTime`: the local date-time the user wants to preserve.
- `offset`: a specific UTC offset, such as `-04:00`.
- `zone`: the region time zone providing the rules for that date-time.
- **Returns**: a `ZonedDateTime` with the exact local date-time, exact zone, and an offset proven to be valid.
- **Invalid combination**: throws `DateTimeException`; for example, a gap or an invalid offset for the zone.
- **Null arguments**: throws `NullPointerException`; validate inputs before calling.
- **No implicit policy**: does not automatically shift the local time or substitute another offset when invalid.

Valid example:

```java
import java.time.*;

LocalDateTime summer = LocalDateTime.of(2026, 7, 1, 9, 30);
ZoneId ny = ZoneId.of("America/New_York");
ZoneOffset offset = ZoneOffset.of("-04:00");

ZonedDateTime meeting = ZonedDateTime.ofStrict(summer, offset, ny);
Instant instant = meeting.toInstant();
// meeting: 2026-07-01T09:30-04:00[America/New_York]
// instant: 2026-07-01T13:30:00Z
```

These are statements placed inside a method. The resulting `meeting` preserves `09:30` and offset `-04:00` in New York. `instant` is the unique confirmed UTC event timestamp.

**Meaning of "strict":** validates **the consistency among the local date-time, offset, and `ZoneId` rules**. It differs from `DateTimeFormatter.withResolverStyle(ResolverStyle.STRICT)`, which checks how a string is parsed into a calendar date/time. You can validly parse `2026-03-08T02:30` into a `LocalDateTime`, yet still not be allowed to schedule an event at that time in New York.

## 4. Looking Up Time Zone Rules Before Creating a ZonedDateTime

`ZoneRules` belongs to the `java.time.zone` package. Obtain it from a zone using `zone.getRules()`, then query valid offsets:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneRules rules = ny.getRules();

List<ZoneOffset> options = rules.getValidOffsets(local);
// [-04:00, -05:00]

boolean allowed = rules.isValidOffset(local, ZoneOffset.of("-05:00"));
// true
```

Key methods:

| Method | Question Answered | Notes |
| --- | --- | --- |
| `getValidOffsets(LocalDateTime)` | Which offsets are valid for the local time? | The list usually has 0, 1, or 2 elements |
| `isValidOffset(local, offset)` | Is the chosen offset in the valid list? | Useful when a client sends an offset |
| `getTransition(LocalDateTime)` | Is there a gap/overlap at this local time and how does the offset transition? | Usually returns `null` when not in a transition |
| `getOffset(Instant)` | At a known UTC instant, what is the zone's offset? | A single value |
| `getOffset(LocalDateTime)` | What offset does the API suggest according to local resolution rules? | Do not use instead of strict validation at gaps/overlaps |

**Common pitfall:** `getOffset(LocalDateTime)` can return an offset based on default rules even during an invalid local time; for strict validation, use `getValidOffsets` or `ofStrict` itself.

### Choosing an Offset Based on Element Count

```java
List<ZoneOffset> valid = rules.getValidOffsets(local);

if (valid.isEmpty()) {
    // Gap: the local time does not exist.
} else if (valid.size() == 1) {
    // Normal: there is exactly one valid offset.
} else {
    // Overlap: two valid offsets; a policy is needed to choose the occurrence.
}
```

The snippet above is conditional logic inside a method, with `rules` and `local` declared beforehand. For strict transactions or appointments, if it falls in an overlap, you should ask the user to choose the offset/occurrence or apply a documented policy. After choosing, use `ofStrict` as a final validation check.

## 5. Normal Case: Valid Offset and Wrong Offset

New York on **2026-07-01** is observing DST, so the correct offset is `-04:00`:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 30);

ZonedDateTime correct = ZonedDateTime.ofStrict(
    local, ZoneOffset.of("-04:00"), ny);
// 2026-07-01T09:30-04:00[America/New_York]
```

However, if the client mistakenly stored the winter offset:

```java
try {
    ZonedDateTime.ofStrict(local, ZoneOffset.of("-05:00"), ny);
} catch (DateTimeException ex) {
    System.out.println("Offset khong hop le");
}
```

The value `-05:00` is a syntactically valid offset and is used in New York on other dates, but it is **invalid for the input local date-time**. Therefore, `ofStrict` throws an exception. It prevents a common bug: computing `09:30-05:00` as `14:30Z` and assuming the New York meeting was confirmed correctly, when the actual timestamp must be `13:30Z`.

If you only use `local.atOffset(ZoneOffset.of("-05:00"))` or `local.toInstant(offset)`, Java does not know about "New York" to validate against. Those two APIs are useful if the input offset is already trusted and the context does not require zone validation.

## 6. DST Gap: Local Time Does Not Exist

On **2026-03-08** in New York, the clock jumps forward from around `01:59:59` to `03:00`. Consequently, `02:30` never happens. Java can still create `LocalDateTime.of(2026,3,8,2,30)` (because it is a valid calendar date and time), but it cannot determine a valid offset for the **New York zone**.

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2026, 3, 8, 2, 30);

List<ZoneOffset> valid = ny.getRules().getValidOffsets(missing);
// [] — gap
```

Because the list is empty, neither `-05:00` nor `-04:00` satisfies "02:30 in New York on that day":

```java
try {
    ZonedDateTime.ofStrict(missing, ZoneOffset.of("-05:00"), ny);
} catch (DateTimeException ex) {
    System.out.println("Gio khong ton tai");
}
```

### How Does ofStrict Differ from atZone at a Gap?

```java
ZonedDateTime automatic = missing.atZone(ny);
// 2026-03-08T03:30-04:00[America/New_York]
```

`atZone` (or `ZonedDateTime.of(local, zone)`) **adjusts** the time across the gap by the transition duration: 02:30 is pushed forward to 03:30. `ofStrict` enforces exactness: it does *not* silently adjust, and instead rejects the combination.

For medical appointment booking, flight scheduling, or transaction cutoffs, implicitly shifting the time can alter what the user intended. You can reject it and ask the user to pick another time, or apply an explicit auto-shift rule per product. Policy is a business decision; `ofStrict` provides the strict check to enforce that policy.

## 7. DST Overlap: The Same Local Time Occurs Twice

On **2026-11-01** in New York, the clock moves back one hour and `01:30` occurs twice:

| Occurrence | LocalDateTime | ZoneOffset | Instant |
| --- | --- | --- | --- |
| First occurrence | `2026-11-01T01:30` | `-04:00` | `2026-11-01T05:30:00Z` |
| Second occurrence | `2026-11-01T01:30` | `-05:00` | `2026-11-01T06:30:00Z` |

`ofStrict` accepts **both combinations** because both offsets are valid at this local time:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2026, 11, 1, 1, 30);

ZonedDateTime first = ZonedDateTime.ofStrict(
    repeated, ZoneOffset.of("-04:00"), ny);

ZonedDateTime second = ZonedDateTime.ofStrict(
    repeated, ZoneOffset.of("-05:00"), ny);

Instant firstInstant = first.toInstant();   // 2026-11-01T05:30:00Z
Instant secondInstant = second.toInstant(); // 2026-11-01T06:30:00Z
```

The two timestamps are **60 real minutes** apart, even though both display 01:30 on the local clock. If you pass offset `-06:00`, `ofStrict` throws `DateTimeException` because it is not a valid offset for the zone.

### Does ofStrict Automatically Pick the First/Second Occurrence?

No. The caller must supply a specific `ZoneOffset`. If the user only selects `01:30` and `America/New_York`, the application needs to display both options or use a communicated policy. `ZonedDateTime.ofLocal(local, zone, preferredOffset)` can prefer an offset if valid but has a fallback; `ofStrict` has no such fallback.

Once a choice is made, store the `Instant` to record the absolute timestamp, and also store `ZoneId` if you need to reconstruct the organizer's local time or build recurring schedule rules.

## 8. Comparing ZonedDateTime Creation APIs

| API | Parameters | On Gap | On Overlap |
| --- | --- | --- | --- |
| `ZonedDateTime.ofStrict(local, offset, zone)` | Full local, offset, zone | Throws exception | Accepts valid offset chosen by caller; rejects other offsets |
| `LocalDateTime.atZone(zone)` | Local + zone | Pushes forward to valid time after gap | Defaults to the earlier offset |
| `ZonedDateTime.of(local, zone)` | Local + zone | Same as `atZone` | Same as `atZone` |
| `ZonedDateTime.ofLocal(local, zone, preferredOffset)` | Local, zone, and preferred offset | Adjusts across gap | Uses preferred if valid, otherwise uses default rule |
| `ZonedDateTime.ofInstant(instant, zone)` | Instant and zone | Unambiguous because instant is already known | Unambiguous |
| `ZonedDateTime.ofInstant(local, offset, zone)` | Local+offset determines instant, then represented in zone | Does not strictly validate local and offset; output local time may change | Computes instant from local+offset |
| `LocalDateTime.atOffset(offset)` | Local + offset | Unaware of zone to validate | Unaware of zone to validate |

In a flow that receives user input to schedule an event at the exact chosen time, `ofStrict` is the right API when you need to confirm that **the requested offset must be valid**. Use `atZone` when the default DST handling policy is acceptable. Use `ofInstant` when you already have an absolute point in time that needs to be displayed in a zone.

A particularly common mistake is using `ofLocal` with the `preferredOffset` parameter as if it were a mandatory offset. If the preferred offset is invalid for the zone, the API may choose another offset; that is not strict behavior.

## 9. Complete Java 17+ Program

Create the file **`ZonedDateTimeStrictDemo.java`**. This program uses fixed data and prints exact results for a normal time, a gap, an overlap, and an invalid offset case.

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

public class ZonedDateTimeStrictDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();

        LocalDateTime summer = LocalDateTime.of(2026, 7, 1, 9, 30);
        ZoneOffset summerOffset = ZoneOffset.of("-04:00");
        ZonedDateTime normal =
                ZonedDateTime.ofStrict(summer, summerOffset, newYork);
        System.out.println("Normal offsets: " + rules.getValidOffsets(summer));
        System.out.println("Normal: " + normal);
        System.out.println("Normal instant: " + normal.toInstant());
        System.out.println("Wrong summer offset valid: " +
                rules.isValidOffset(summer, ZoneOffset.of("-05:00")));

        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        System.out.println("Gap offsets: " + rules.getValidOffsets(gap));
        System.out.println("Gap default: " + gap.atZone(newYork));
        boolean gapRejected = false;
        try {
            ZonedDateTime.ofStrict(gap, ZoneOffset.of("-05:00"), newYork);
        } catch (DateTimeException ex) {
            gapRejected = true;
        }
        System.out.println("Gap strict rejected: " + gapRejected);

        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> overlapOffsets = rules.getValidOffsets(overlap);
        System.out.println("Overlap offsets: " + overlapOffsets);
        ZonedDateTime earlier =
                ZonedDateTime.ofStrict(overlap, overlapOffsets.get(0), newYork);
        ZonedDateTime later =
                ZonedDateTime.ofStrict(overlap, overlapOffsets.get(1), newYork);
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());
        System.out.println("Different instant: " +
                !earlier.toInstant().equals(later.toInstant()));

        boolean invalidRejected = false;
        try {
            ZonedDateTime.ofStrict(overlap, ZoneOffset.of("-06:00"), newYork);
        } catch (DateTimeException ex) {
            invalidRejected = true;
        }
        System.out.println("Invalid overlap offset rejected: " + invalidRejected);
    }
}
```

Run in the directory containing the file using JDK 17 or later:

```bash
javac -encoding UTF-8 ZonedDateTimeStrictDemo.java
java ZonedDateTimeStrictDemo
```

**Verified stdout:**

```text
Normal offsets: [-04:00]
Normal: 2026-07-01T09:30-04:00[America/New_York]
Normal instant: 2026-07-01T13:30:00Z
Wrong summer offset valid: false
Gap offsets: []
Gap default: 2026-03-08T03:30-04:00[America/New_York]
Gap strict rejected: true
Overlap offsets: [-04:00, -05:00]
Earlier instant: 2026-11-01T05:30:00Z
Later instant: 2026-11-01T06:30:00Z
Different instant: true
Invalid overlap offset rejected: true
```

Output analysis: in July, New York has offset `-04:00`; `-05:00` is invalid for that time. The gap time has no valid offset and is automatically shifted by `atZone`, whereas `ofStrict` rejects it. The overlap time has two valid offsets, producing two different instants; `-06:00` is rejected.

The New York rules in the example depend on the JDK's timezone data (tzdb) for 2026. If local laws change, future results may differ after a JDK/tzdb update.

## 10. Designing a Practical Resolver

A scheduling API might receive:

```json
{
  "localStart": "2026-11-01T01:30:00",
  "timeZone": "America/New_York",
  "selectedOffset": "-05:00"
}
```

Here the user chose the **second occurrence** of 01:30 in New York, corresponding to `2026-11-01T06:30:00Z`. The server needs to parse the three fields, check the list of valid offsets, and only then create and store the timestamp.

Recommended flow:

1. Parse `localStart` into `LocalDateTime`; parse `timeZone` into `ZoneId` (return an error if the zone is unsupported).
2. Parse `selectedOffset` into `ZoneOffset` if present. If absent, leave it null and decide based on the zone's state.
3. Retrieve `valid = zone.getRules().getValidOffsets(local)`.
4. If `valid` is empty, report that the time does not exist. If there is 1 offset, use that offset; if the request sent a different offset, report an incompatibility error.
5. If there are 2 offsets, require the caller to choose one value from the list according to business policy.
6. Call `ZonedDateTime.ofStrict(local, chosenOffset, zone)` to guarantee validity before saving.
7. Store `toInstant()` as the UTC timestamp, along with `ZoneId` if you need to preserve the organizer's zone context or recurring schedule.

### Example Java 17+ Resolver Class

Save as **`StrictMeetingResolver.java`** if you want to integrate it into an application:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Objects;

public final class StrictMeetingResolver {
    private StrictMeetingResolver() {}

    public static Instant resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset requestedOffset) {

        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> valid = rules.getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Gio dia phuong khong ton tai trong mui gio");
        }

        ZoneOffset chosen;
        if (valid.size() == 1) {
            chosen = valid.get(0);
            if (requestedOffset != null && !chosen.equals(requestedOffset)) {
                throw new IllegalArgumentException(
                        "Offset khong hop le cho ngay gio va vung");
            }
        } else {
            if (requestedOffset == null) {
                throw new IllegalArgumentException(
                        "Gio trung: can chon offset");
            }
            if (!valid.contains(requestedOffset)) {
                throw new IllegalArgumentException("Offset khong hop le");
            }
            chosen = requestedOffset;
        }

        return ZonedDateTime.ofStrict(local, chosen, zone).toInstant();
    }
}
```

This is a library class without `main()`, which can be compiled separately:

```bash
javac -encoding UTF-8 StrictMeetingResolver.java
```

Usage in a service or unit test:

```java
Instant confirmed = StrictMeetingResolver.resolve(
    LocalDateTime.of(2026, 11, 1, 1, 30),
    ZoneId.of("America/New_York"),
    ZoneOffset.of("-05:00"));
// 2026-11-01T06:30:00Z
```

Resolver policy: **gaps are rejected**, **overlaps require an explicit offset choice**, and normal times automatically pick the single valid offset if the request omits it. This is a clear example policy; a real application may choose a different policy, but it should make it visible to the user. Ensure business error messages match the UI language.

### What If the Client Only Sends Local Time and Zone?

When the offset is missing and the zone is in an overlap, you cannot be sure which timestamp the user intended. The server should return a list of options with offsets and "first/second occurrence" information, or a status requiring confirmation. You should not pick one silently without notifying the UI. Once resolved, store:

```json
{
  "startInstant": "2026-11-01T06:30:00Z",
  "organizerZone": "America/New_York"
}
```

`startInstant` allows sorting events and computing actual durations; `organizerZone` helps display the event time in the right zone and supports future local rules. Storing only a `LocalDateTime` during an overlap loses the occurrence selection information.

## 11. Storage and Testing

### 11.1. Data Design

| Data | Java Type | When Needed |
| --- | --- | --- |
| User-entered date-time | `LocalDateTime` | Before resolving against a zone |
| Selected offset | `ZoneOffset` | Especially during an overlap |
| Organizer zone | `ZoneId` | Preserving zone context and history/rules |
| Confirmed event timestamp | `Instant` | Storing the confirmed event record |
| Actual duration | `Duration` between two `Instant`s | Measuring elapsed time accurately across DST |

The SQL types `TIMESTAMP WITHOUT TIME ZONE` and `TIMESTAMP WITH TIME ZONE` have different semantics across databases. Many databases do not preserve the IANA zone ID in a timestamp column; if you need to reconstruct `America/New_York`, store the zone ID separately. Never apply the server's timezone to a bare local string from a request.

### 11.2. Required Test Suite

| Case | Input | Expected Result |
| --- | --- | --- |
| Normal summer | `2026-07-01 09:30`, NY, `-04:00` | Success: `2026-07-01T13:30Z` |
| Wrong summer offset | Same local/NY, `-05:00` | `DateTimeException` |
| Gap | `2026-03-08 02:30`, NY, `-05:00` | `DateTimeException` |
| Gap with new offset | Same local/NY, `-04:00` | `DateTimeException` |
| Overlap first occurrence | `2026-11-01 01:30`, NY, `-04:00` | `05:30Z` |
| Overlap second occurrence | Same local/NY, `-05:00` | `06:30Z` |
| Wrong overlap offset | Same local/NY, `-06:00` | `DateTimeException` |
| Normal winter time | `2026-12-01 09:30`, NY, `-05:00` | Success |
| Fixed-offset zone | `2026-07-01 09:30`, zone `+07:00` and offset `+07:00` | Success |
| Resolver missing offset in overlap | Overlap time and null offset | Error requiring selection |
| Null input | `ofStrict(null, offset, zone)` | `NullPointerException` |
| Unknown zone ID | `ZoneId.of("No/Such_Zone")` | Unsupported zone ID error |

Test with explicit date-times, offsets, and zones so tests do not depend on the system clock. If a service adds a condition like "appointment must be in the future", inject a `Clock` into the service, use `Clock.fixed(...)` in tests, and then compare **two resolved `Instant`s**. Avoid calling `LocalDateTime.now()` using the CI server's default timezone.

### 11.3. Notes on tzdb and Future Times

Zone rules can change when local laws are amended and the JDK updates tzdb. A confirmed point in time should be stored as an `Instant`; to preserve the organizer's local representation, also store the `ZoneId` and the offset selection data if auditing is required. A recurring schedule like "09:00 Monday in New York" must apply zone rules to each occurrence rather than hardcoding a current offset.

## 12. Common Mistakes

1. **Using `atZone` and assuming every local time is valid.** At a gap, `atZone` shifts the time by default; `ofStrict` rejects it.
2. **Storing only `LocalDateTime` and `ZoneId` during an overlap.** You cannot distinguish the two 01:30 occurrences without the offset choice or `Instant`.
3. **Assuming `ofStrict` picks the offset automatically.** The caller must supply the offset; if it is wrong, the API throws an exception.
4. **Confusing `DateTimeFormatter` strictness with `ZonedDateTime` strictness.** One checks date/time string parsing; the other checks the offset against zone rules.
5. **Using the winter offset for a summer meeting.** An offset may be valid on another date but wrong for the date in question.
6. **Using `ZoneOffset` as a region name.** An offset does not contain a city's DST rules.
7. **Calling `getOffset(LocalDateTime)` for strict input validation.** Use `getValidOffsets`/`isValidOffset` instead.
8. **Using `ofLocal` with a preferred offset as a strict check.** `ofLocal` may fall back when the preferred offset is invalid.
9. **Trying to recover the zone name solely from `Instant` or `ZoneOffset`.** An absolute timestamp and a standalone offset do not record the original region identity.
10. **Falling back to `ZoneId.systemDefault()` when the request has an explicit zone.** That makes results depend on the server.
11. **Comparing events by local time strings.** Two identical local times in an overlap can be two different instants.
12. **Keeping a fixed offset for future recurring schedules.** DST changes the offset; you need the zone ID and must apply rules per occurrence.
13. **Catching the exception and silently adjusting the time without a policy.** You should return an error, ask the user to choose again, or apply a transparent policy.
14. **Assuming all calendar day intervals are 24 hours.** Across DST, adding one local day and adding 24 hours on the timeline can differ.

## 13. Practice Exercises

### Exercise 1 — Summer Validation

Given `LocalDateTime.of(2026,7,1,9,30)` and `America/New_York`. Try `ofStrict` with `-04:00` and `-05:00`, and explain why only one combination is valid. On success, print `toInstant()`.

### Exercise 2 — Same Local Time, Two Instants

Create `LocalDateTime.of(2026,11,1,1,30)`. Retrieve the list of valid offsets for New York, call `ofStrict` for both, and check `Duration.between(first.toInstant(), second.toInstant()).toMinutes()`. Expect `60` minutes.

### Exercise 3 — Gap and Policy

For `2026-03-08T02:30` in New York, prove that `getValidOffsets` is empty; try `ofStrict` with both the pre-DST and post-DST offsets. Compare the behavior with `atZone`. Write an error message guiding the user to choose an existing time.

### Exercise 4 — API with Offset Selection

Design a request containing `localStart`, `timeZone`, and `selectedOffset`; when there is 1 offset, `selectedOffset` can be omitted; when there are 2 offsets, require a selection; when there are 0 offsets, return an error. Return `Instant` and `ZoneId` on successful confirmation.

### Exercise 5 — Unit Tests

Write JUnit 5 tests for the resolver: normal, gap, overlap missing selection, overlap choosing first occurrence, choosing second occurrence, wrong offset, and nonexistent zone. Assert the expected exceptions and instant results; do not rely on the machine's current time.

## 14. Completion Checklist

- [ ] Describe the three arguments of `ZonedDateTime.ofStrict(local, offset, zone)`.
- [ ] Distinguish `LocalDateTime`, `ZoneOffset`, `ZoneId`, `ZonedDateTime`, and `Instant`.
- [ ] Know why an offset can be valid on one date but invalid on another date in the same zone.
- [ ] Detect a DST gap by an empty offset list and a DST overlap by two offsets.
- [ ] Understand that `ofStrict` rejects invalid combinations instead of silently adjusting them.
- [ ] Distinguish `ofStrict`, `atZone`, `ofLocal`, `atOffset`, and `ofInstant`.
- [ ] Choose a clear display/UI policy when a local time is ambiguous.
- [ ] Convert the validated object to `Instant` to store an absolute event.
- [ ] Thoroughly test success, wrong offset, gap, overlap, and seasonal time cases.
- [ ] Avoid relying on the machine's timezone or "current" offset to calculate future schedules.

## Official Java 17 Documentation

- [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [ZoneOffset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html)
- [ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [DateTimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DateTimeException.html)
