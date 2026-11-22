# Combining LocalDateTime with ZoneId or ZoneOffset to Determine an Instant

## 1. Core Idea: Local Time Is Not Yet an Absolute Point in Time

`LocalDateTime` in Java 17+ describes **a date and time on a local clock** (year, month, day, hour, minute, second, nanosecond), but **does not contain a time zone (`ZoneId`) or UTC offset (`ZoneOffset`)**. For example:

```java
import java.time.LocalDateTime;

LocalDateTime meeting = LocalDateTime.of(2026, 7, 1, 9, 30);
// 2026-07-01T09:30
```

The data above only states "09:30 on 2026-07-01", not "09:30 where". If that is Ho Chi Minh City time (`Asia/Ho_Chi_Minh`, UTC+07 on this date), the corresponding instant is **02:30 UTC**. If that is Tokyo time (`Asia/Tokyo`, UTC+09), the corresponding instant is **00:30 UTC**. The same `LocalDateTime` can correspond to different `Instant` values.

To determine a point on the timeline, you need **local date-time + a valid offset**. `ZoneOffset` provides the offset directly. A region-based `ZoneId` (for example `America/New_York`) provides **rules for determining the offset by date**, including historical changes and Daylight Saving Time (DST). There are even times when **a local date-time + ZoneId is still not enough to yield a unique Instant**: the time may not exist (gap) or may occur twice (overlap). This lesson explains when Java's rules can be applied automatically and when you must consult business policy.

**Objectives:** know how to use `atZone(...)` and `atOffset(...)`, convert to `Instant`, handle DST, distinguish between region and offset, convert time zones, and store/test data without getting the wrong point in time.

### Five Related Data Types

| Type | What does it hold? | Example | Determines an `Instant`? |
| --- | --- | --- | --- |
| `LocalDateTime` | Local date + time; no offset/zone | `2026-07-01T09:30` | Not yet |
| `ZoneOffset` | Difference from UTC at an instant, e.g. `+07:00` | `+07:00` | Yes, together with LocalDateTime |
| `ZoneId` | Region ID and zone rules over time | `Asia/Ho_Chi_Minh` | Usually yes with LocalDateTime, but gap/overlap must be resolved |
| `OffsetDateTime` | LocalDateTime + ZoneOffset | `2026-07-01T09:30+07:00` | Yes |
| `ZonedDateTime` | LocalDateTime + ZoneId + valid offset | `2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]` | Yes |
| `Instant` | Absolute point on the UTC timeline | `2026-07-01T02:30:00Z` | Is itself the absolute point |

`LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, and `Instant` are all **immutable** and value-based: conversions, additions/subtractions, and field adjustments return a new object. Use `equals` or semantically appropriate time comparison methods; do not rely on `==`.

## 2. Combining LocalDateTime with ZoneOffset

`ZoneOffset` represents a fixed UTC offset (for example `+07:00`). When you **already know the exact offset to use**, Java can map a `LocalDateTime` directly to a UTC instant without looking up region rules.

### 2.1. Using `atOffset`

```java
import java.time.*;

LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 30);
ZoneOffset offset = ZoneOffset.of("+07:00");

OffsetDateTime withOffset = local.atOffset(offset);
Instant instant = withOffset.toInstant();

// withOffset: 2026-07-01T09:30+07:00
// instant:    2026-07-01T02:30:00Z
```

This is a **code snippet for use inside a class/method**, not a standalone runnable file. `atOffset` creates an `OffsetDateTime`, keeping the local time `09:30` and attaching the offset `+07:00`. `toInstant()` obtains the UTC instant: `09:30 − 07:00 = 02:30 UTC`.

You can use the shortcut:

```java
Instant sameInstant = local.toInstant(offset);
```

The `LocalDateTime.toInstant(ZoneOffset)` method computes the instant using the specified offset, but **does not verify whether that offset is valid for any IANA region**. If you pass `+09:00` for data that belongs to Ho Chi Minh City (`+07:00`), Java still computes an Instant, but you have chosen the wrong business instant:

```java
Instant correct = local.toInstant(ZoneOffset.ofHours(7));
// 2026-07-01T02:30:00Z

Instant wrongForHcm = local.toInstant(ZoneOffset.ofHours(9));
// 2026-07-01T00:30:00Z — two hours off from the Ho Chi Minh City instant
```

**Only use an offset directly** when the protocol/input data already provides the exact offset (`2026-07-01T09:30+07:00`), or when the problem truly defines a fixed offset. An offset like `-05:00` cannot substitute for the `America/New_York` region rules during DST months.

### 2.2. An Offset Is Not a Region Name

`ZoneOffset.of("+07:00")` is a `ZoneOffset` and also extends `ZoneId` in the Java API, but **semantically** it only holds a fixed offset. `ZoneId.of("Asia/Ho_Chi_Minh")` is a region name; a region has offset data for each point in time. Some regions may change their rules due to DST or legal regulations.

`OffsetDateTime` remembers the specific offset **when the data was created**. It cannot infer the original region name, DST rules, or whether that offset remains valid in another year.

Use `ZoneOffset.UTC` when the data is truly UTC; `Z` in ISO 8601 means UTC offset zero.

## 3. Combining LocalDateTime with ZoneId

`ZoneId` is a time zone identifier, usually from the IANA database (for example `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York`). Given a valid local date-time, Java finds the appropriate offset according to the region's **`ZoneRules`** at that date and time.

### 3.1. Common Approach: `local.atZone(zone)`

```java
import java.time.*;

LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();

// zoned : 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
// instant: 2026-07-01T02:30:00Z
```

`ZonedDateTime` carries the local date-time, the region name, **and the resolved offset**. You can query:

- `zoned.toLocalDateTime()` → the local value after zone resolution.
- `zoned.getZone()` → the zone, here `Asia/Ho_Chi_Minh`.
- `zoned.getOffset()` → the specific offset at this point in time, here `+07:00`.
- `zoned.toInstant()` → the actual UTC instant.
- `zoned.toOffsetDateTime()` → the date-time + current offset; the result drops the zone ID.

You can equivalently write `ZonedDateTime.of(local, zone)`. For normal local times, this is convenient and sufficient; for **gaps/overlaps**, both default methods have **an implicit policy** explained in detail in the DST section.

### 3.2. Relationship Between local + zone + offset

Conceptually:

```text
LocalDateTime: 2026-07-01T09:30
        + ZoneId: Asia/Ho_Chi_Minh
                  |
                  v
        ZoneRules determines offset +07:00
                  |
                  v
ZonedDateTime: 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
                  |
                toInstant()
                  |
                  v
Instant: 2026-07-01T02:30:00Z
```

Correspondingly, when you already have an offset from a trusted source:

```text
LocalDateTime: 2026-07-01T09:30
        + ZoneOffset: +07:00
                  |
                atOffset()
                  |
                  v
OffsetDateTime: 2026-07-01T09:30+07:00
                  |
                toInstant()
                  |
                  v
Instant: 2026-07-01T02:30:00Z
```

**Important point:** both paths produce the same `Instant` **when the chosen offset is the valid offset and they match**. If a user supplies a different offset, the `atOffset` path can produce a different instant without Java reporting any error.

### 3.3. Choosing the Right Region Instead of the Server Time Zone

`ZoneId.systemDefault()` gets the default time zone of the machine currently running. For servers, CI, containers, and multi-country features, this easily produces different results when the environment changes. Store/pass the time zone **from business requirements**, for example:

- User booking an appointment in Ho Chi Minh City → `ZoneId.of("Asia/Ho_Chi_Minh")`.
- Meeting in New York time → `ZoneId.of("America/New_York")`.
- Reminder app in the user's local time → store the user's zone ID; do not guess from language, country, or current offset.

Do not rely on ambiguous abbreviations such as `CST` to infer a unique region; prefer official zone IDs.

## 4. Why LocalDateTime + ZoneId Sometimes Does Not Uniquely Determine an Instant

### 4.1. DST Gap: A Non-Existent Time

When clocks spring forward, a span of local time never occurs. In **America/New_York** on **2026-03-08**, clocks jump from `01:59:59...` to `03:00`. Therefore:

```java
LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
ZoneId ny = ZoneId.of("America/New_York");
ZonedDateTime adjusted = gap.atZone(ny);

// adjusted: 2026-03-08T03:30-04:00[America/New_York]
```

By default, Java **pushes the non-existent time forward by the length of the gap**. Thus `02:30` becomes `03:30`. For scheduling apps, flight schedules, or business logic requiring exact times, shifting the time automatically may be inappropriate. Detect the gap first and decide whether to **reject, ask again, or shift** according to a defined rule.

### 4.2. DST Overlap: An Hour That Occurs Twice

In **America/New_York** on **2026-11-01**, clocks fall back one hour. `01:30` occurs twice:

| Occurrence | Local Time | Offset | Instant |
| --- | --- | --- | --- |
| First (DST) | `2026-11-01T01:30` | `-04:00` | `2026-11-01T05:30:00Z` |
| Second (standard time) | `2026-11-01T01:30` | `-05:00` | `2026-11-01T06:30:00Z` |

Both are valid points in time, separated by **60 actual minutes**. By default, `local.atZone(ny)` picks **the earlier offset in the overlap**, which is usually the summer offset `-04:00`. If business logic wants the later occurrence, use `withLaterOffsetAtOverlap()` or explicitly resolve the `ZoneOffset` chosen by the user.

### 4.3. Using ZoneRules to Check the Three States

`ZoneRules` is in `java.time.zone`, obtained from `ZoneId.getRules()`. Call `getValidOffsets(local)` to find the valid offsets for **a local date-time**:

- **0 offsets:** gap (the time does not exist).
- **1 offset:** normal time; resolves to a single Instant.
- **2 offsets:** overlap; must choose the first or second occurrence if business logic requires unique determination.

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneRules rules = ny.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    throw new IllegalArgumentException("Gio dia phuong khong ton tai");
} else if (offsets.size() == 2) {
    // Ask the caller to specify the desired offset.
} else {
    ZonedDateTime resolved = ZonedDateTime.ofStrict(local, offsets.get(0), ny);
}
```

This is an **illustrative snippet placed inside a method**, not a complete program. When there are two offsets, the flow should ask the user or system to choose one valid offset, then call:

```java
ZonedDateTime selected =
    ZonedDateTime.ofStrict(local, chosenValidOffset, ny);
Instant finalInstant = selected.toInstant();
```

`ZonedDateTime.ofStrict(...)` checks **whether the supplied offset is valid for the local datetime in that zone**. If the local time falls in a gap or the offset is wrong, it throws `DateTimeException` instead of silently adjusting the time. For an overlap, either valid offset can create a distinct instant.

### 4.4. Special Rules in ZonedDateTime Creation APIs

| API | Gap | Overlap |
| --- | --- | --- |
| `local.atZone(zone)` / `ZonedDateTime.of(local, zone)` | Automatically shifts to valid time after gap | Defaults to the earlier offset (usually summer time) |
| `ZonedDateTime.ofStrict(local, offset, zone)` | Rejects because no offset is valid | Accepts the valid offset chosen by caller; rejects any other offset |
| `ZonedDateTime.ofLocal(local, zone, preferredOffset)` | Shifts past gap | Uses preferred offset if valid; otherwise picks default |
| `zoned.withEarlierOffsetAtOverlap()` | Unchanged if not in overlap | Picks the first occurrence |
| `zoned.withLaterOffsetAtOverlap()` | Unchanged if not in overlap | Picks the later occurrence |

Although the examples use New York in 2026, time zone rules are provided by the tzdb database and JDK version; for applications forecasting schedules far into the future, rules may be updated when local policies change.

### 4.5. Inspecting Transition Details

`rules.getTransition(local)` normally returns a `ZoneOffsetTransition` at a gap/overlap, allowing you to get `getOffsetBefore()`, `getOffsetAfter()`, `getDuration()`, `isGap()`, or `isOverlap()`. During normal time, `getTransition(local)` returns `null`. Only use it when you need exact transition messages or rules; `getValidOffsets` is sufficient for common branching.

## 5. Converting Time Zones After an Instant Is Determined

If you already have a concrete event, for example `Instant.parse("2026-07-01T02:30:00Z")`, you can display the same event in any zone:

```java
import java.time.*;

Instant event = Instant.parse("2026-07-01T02:30:00Z");
ZonedDateTime hcm = event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime newYork = event.atZone(ZoneId.of("America/New_York"));
// hcm:     2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
// newYork: 2026-06-30T22:30-04:00[America/New_York]
```

The two variables have different clock dates/times, yet `hcm.toInstant().equals(newYork.toInstant())` is `true`.

Distinguish two commonly misused methods:

- `zoned.withZoneSameInstant(otherZone)`: **keeps the same actual instant**, changing the display according to the new zone. Use when converting a meeting schedule across countries.
- `zoned.withZoneSameLocal(otherZone)`: **tries to keep the local clock date and time**, changing the zone and resolving a new offset; **the actual instant may change**. Use when intentionally moving 09:30 in the old zone's time to 09:30 in the new zone's time.

For example, a meeting starting at `09:30` in Ho Chi Minh City (UTC+07) on 2026-07-01: `withZoneSameInstant(New_York)` gives **22:30 on 2026-06-30**, whereas `withZoneSameLocal(New_York)` tries to represent **09:30 on 2026-07-01 in New York**, which corresponds to **13:30 UTC**; the two operations serve different purposes. `ZoneId` itself is not data that must be permanently tied to an `Instant`: an absolute point in time exists independently of location.

### 5.1. Keeping Local Time or Keeping UTC Instant When Adding Time?

`ZonedDateTime` may have to handle DST when adding/subtracting time:

- `zoned.plusDays(1)` adds **one local calendar day**, keeping the clock time if still valid; across DST, the actual elapsed duration may be 23 or 25 hours.
- `zoned.plusHours(24)` adds **24 hours on the timeline** according to instant semantics; the clock time may change across a DST transition.
- `Duration.between(start.toInstant(), end.toInstant())` measures actual elapsed time; `Period.between(start.toLocalDate(), end.toLocalDate())` measures calendar day distance.

For a rule like "deliver at 09:00 tomorrow local time", use calendar arithmetic with `ZoneId`. For "exactly 24 hours after receiving the request", use `Instant.plus(Duration.ofHours(24))`.

## 6. Converting Back: Instant + ZoneId to LocalDateTime

`Instant` has enough information to know the UTC point in time, but does not by itself indicate the clock at a specific place. When you need to **display** or calculate dates for a region, provide the zone:

```java
import java.time.*;

Instant event = Instant.parse("2026-07-01T02:30:00Z");
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime local = LocalDateTime.ofInstant(event, hcm);
// local: 2026-07-01T09:30

ZonedDateTime zoned = event.atZone(hcm);
// zoned: 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
```

`LocalDateTime.ofInstant(instant, zone)` and `instant.atZone(zone).toLocalDateTime()` can produce the same local value. However, **the returned LocalDateTime has stripped away the zone and UTC instant information**: if serialized as a bare string `2026-07-01T09:30`, another application cannot guess that it is Ho Chi Minh City time.

**Round-trip rule**: if you keep both `Instant` and `ZoneId`, you can reconstruct the zoned representation. If you only keep `LocalDateTime`, you must rely on external context to re-determine the instant; during an overlap, you sometimes also need the resolved offset/choice.

## 7. Receiving and Parsing ISO 8601 Data

Different string formats represent different semantics:

| String | Appropriate Type | Sufficient to Determine an Instant? |
| --- | --- | --- |
| `2026-07-01T09:30:00` | `LocalDateTime` | Not yet |
| `2026-07-01T09:30:00+07:00` | `OffsetDateTime` | Yes |
| `2026-07-01T09:30:00+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | Yes |
| `2026-07-01T02:30:00Z` | `Instant` | Yes |

```java
import java.time.*;

LocalDateTime noZone = LocalDateTime.parse("2026-07-01T09:30:00");

OffsetDateTime fixedOffset =
    OffsetDateTime.parse("2026-07-01T09:30:00+07:00");

ZonedDateTime withZone = ZonedDateTime.parse(
    "2026-07-01T09:30:00+07:00[Asia/Ho_Chi_Minh]");

Instant utc = Instant.parse("2026-07-01T02:30:00Z");
```

The strings above represent the same clock/instant as in the examples, when the zone and offset are compatible. If a user enters `dd/MM/uuuu HH:mm`, use `DateTimeFormatter` from `java.time.format` to parse the exact pattern and then **attach the ZoneId/ZoneOffset according to business rules**; do not force a timezone format onto source data that does not yet have a timezone.

### 7.1. Validate the Zone Offset When Input Contains Both

A string containing both an offset and a zone ID may carry an offset that is invalid for that date-time under the zone's rules. When data comes from outside, validate consistency using `ZonedDateTime.ofStrict(local, offset, zone)` on the parsed components or check `zone.getRules().isValidOffset(local, offset)` before using it in business logic. Do not assume that just because a string parses successfully, the offset matches the intended region; some timezone-handling APIs adjust or prioritize the instant during parsing.

For example, in July 2026 in New York, the valid offset is `-04:00`, not `-05:00`. `LocalDateTime.of(2026,7,1,9,30).atOffset(ZoneOffset.ofHours(-5))` is still a valid `OffsetDateTime`, but **incorrect** if the explicit requirement is "09:30 in New York".

### 7.2. A String Without an Offset Has No Implicit Timezone

If an API receives:

```json
{
  "startsAt": "2026-07-01T09:30:00"
}
```

you must not automatically assume UTC, the server's timezone, IP-based timezone, browser locale, or the current offset. The contract should add `"timeZone": "Asia/Ho_Chi_Minh"`, or accept an ISO string that already includes an offset and define how it is used.

Invalid data (non-existent hour, February 31, unrecognized zone ID) can throw `DateTimeParseException` or `DateTimeException`. Validate at the input boundary, return specific error messages, and avoid unintended automatic time adjustments.

## 8. Standalone Java 17+ Summary Program

Create the file **`LocalDateTimeZoneDemo.java`**, and enter the exact content below:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.zone.ZoneRules;
import java.util.List;

public class LocalDateTimeZoneDemo {
    public static void main(String[] args) {
        LocalDateTime meeting = LocalDateTime.of(2026, 7, 1, 9, 30);
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = meeting.atZone(hcm);
        OffsetDateTime offsetBased = meeting.atOffset(ZoneOffset.ofHours(7));
        System.out.println("Local: " + meeting);
        System.out.println("Zoned: " + zoned);
        System.out.println("Instant zone: " + zoned.toInstant());
        System.out.println("Instant offset: " + offsetBased.toInstant());
        System.out.println("Same instant: " +
                zoned.toInstant().equals(offsetBased.toInstant()));

        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        System.out.println("Gap options: " + rules.getValidOffsets(gap).size());
        System.out.println("Gap default: " + gap.atZone(newYork));

        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> options = rules.getValidOffsets(overlap);
        System.out.println("Overlap options: " + options);
        ZonedDateTime early = ZonedDateTime.ofStrict(overlap, options.get(0), newYork);
        ZonedDateTime late = ZonedDateTime.ofStrict(overlap, options.get(1), newYork);
        System.out.println("First occurrence: " + early.toInstant());
        System.out.println("Second occurrence: " + late.toInstant());
        System.out.println("Gap/overlap elapsed minutes: " +
                Duration.between(early.toInstant(), late.toInstant()).toMinutes());
        System.out.println("New York clock for HCM meeting: " +
                zoned.withZoneSameInstant(newYork).toLocalDateTime());
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac -encoding UTF-8 LocalDateTimeZoneDemo.java
java LocalDateTimeZoneDemo
```

**Expected output for the 2026 data and time zone rules in the example:**

```text
Local: 2026-07-01T09:30
Zoned: 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
Instant zone: 2026-07-01T02:30:00Z
Instant offset: 2026-07-01T02:30:00Z
Same instant: true
Gap options: 0
Gap default: 2026-03-08T03:30-04:00[America/New_York]
Overlap options: [-04:00, -05:00]
First occurrence: 2026-11-01T05:30:00Z
Second occurrence: 2026-11-01T06:30:00Z
Gap/overlap elapsed minutes: 60
New York clock for HCM meeting: 2026-06-30T22:30
```

**Explanation:**

1. `meeting` is a `LocalDateTime` without a UTC instant; after `atZone(hcm)`, we get a `ZonedDateTime` with offset +07.
2. `meeting.atOffset(+07)` creates an `OffsetDateTime`; in this case both ways produce **the exact same Instant** because the offset matches the zone offset.
3. The gap time in New York has no valid offset. `atZone` defaults to shifting to `03:30 -04:00`; a scheduling app should detect this if the adjustment is unacceptable.
4. The overlap has two offsets. `ZonedDateTime.ofStrict(...)` produces two different instants, 60 minutes apart on the timeline.
5. `withZoneSameInstant(newYork)` preserves the meeting instant, but the clock in New York becomes `22:30 on 06/30` (the previous day).

*Minor note:* The output label `Gap/overlap elapsed minutes` is just the printed label in the demo; the value 60 is computed between **the two choices in the overlap**, not between the gap and the overlap.

## 9. Designing Data Correctly for Applications

### 9.1. Models for Different Use Cases

| Use Case | Recommended Field | Why |
| --- | --- | --- |
| Transaction created/updated timestamp | `Instant` | Has a clear UTC instant; easy to compare |
| Birthday, calendar-only expiration date | `LocalDate` | Calendar dates do not depend on a zone |
| Daily opening hours | `LocalTime` + facility `ZoneId` if needed | Does not yet specify a concrete occurrence date |
| Confirmed appointment | `Instant`; plus `ZoneId` to retain organizer/display zone | Instant is fixed; store zone if context is needed |
| User selecting an appointment | `LocalDateTime` + `ZoneId` + offset choice on overlap | Cannot yet store a unique instant in all cases |
| Rule "every Monday at 09:00 in New York" | Local date/time, `ZoneId`, and recurrence rule | Offset changes by season, cannot be modeled by a single `Instant` |
| System receiving datetime with `+07:00` from API | `OffsetDateTime` then `toInstant` | Offset provides enough information to resolve the instant |

### 9.2. A Safe JSON Example for Appointments

User request stage:

```json
{
  "localStart": "2026-11-01T01:30:00",
  "timeZone": "America/New_York",
  "selectedOffset": "-05:00"
}
```

The application must validate that `selectedOffset` is one of the valid offsets at `localStart` in `timeZone` before creating an `Instant`. After confirmation, it can store:

```json
{
  "startInstant": "2026-11-01T06:30:00Z",
  "organizerZone": "America/New_York"
}
```

If you need to support rescheduling by **the scheduled local time**, you can also retain the original `localStart`/offset chosen by the user according to the contract; however, `startInstant` remains the reference for comparisons and sending invitations across multiple time zones. Do not simply store `"2026-11-01T01:30"` and guess the offset only when the event fires.

### 9.3. Database/ORM and Timestamps

- For records of absolute instants, prefer normalizing to `Instant` or a datetime structure with an explicit offset as supported by the driver/DB.
- `TIMESTAMP WITHOUT TIME ZONE` typically only stores date-time values without a zone. If an application uses this type to store `LocalDateTime` without a UTC or zone contract, it easily causes discrepancies when read back.
- `TIMESTAMP WITH TIME ZONE` behaves differently across RDBMSs and usually **does not preserve the IANA region ID**. Choose the SQL type after reading the specific DBMS documentation and driver mapping; if you want to keep `America/New_York`, store the zone ID separately.
- When the original input is a UTC timestamp, do not convert it to the server's `LocalDateTime` and save it without the zone; doing so loses information about the true point in time.

### 9.4. Rules for Recurring Schedules

A schedule like "09:00 AM every Monday in New York" needs to generate **the local date-time for each occurrence date**, look up `ZoneRules` for that date, handle gap/overlap according to policy, and finally convert each occurrence to an `Instant`. Do not create one `Instant` and keep adding 7×24 hours indefinitely because of weeks with DST changes or zone rule updates. Nor should you store a fixed `-05:00` offset if the schedule must stay at 09:00 New York time during summer as well.

## 10. Designing an Explicit Resolver for Business Logic

The class below is independent of how the user inputs data. It **rejects gaps**, **rejects overlaps when an offset choice is missing**, and uses strict validation to determine an absolute instant. This is the implementation approach when you do not want `atZone` to shift times implicitly.

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Objects;

public final class MeetingTimeResolver {
    public static Instant resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset requestedOffset) {

        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> validOffsets = rules.getValidOffsets(local);

        if (validOffsets.isEmpty()) {
            throw new IllegalArgumentException(
                    "Giờ địa phương không tồn tại trong múi giờ đã chọn");
        }

        ZoneOffset selected;
        if (validOffsets.size() == 1) {
            selected = validOffsets.get(0);
            if (requestedOffset != null && !requestedOffset.equals(selected)) {
                throw new IllegalArgumentException("Offset không hợp lệ");
            }
        } else {
            if (requestedOffset == null) {
                throw new IllegalArgumentException(
                        "Giờ trùng: cần chọn offset");
            }
            if (!validOffsets.contains(requestedOffset)) {
                throw new IllegalArgumentException("Offset không hợp lệ");
            }
            selected = requestedOffset;
        }

        return ZonedDateTime.ofStrict(local, selected, zone).toInstant();
    }

    private MeetingTimeResolver() {}
}
```

This is a **self-compiling library class**, but it has no `main` method; it must be called from a test, controller, or service. To compile this class on its own, save it as `MeetingTimeResolver.java` and run:

```bash
javac -encoding UTF-8 MeetingTimeResolver.java
```

How to call it inside a method:

```java
Instant chosen = MeetingTimeResolver.resolve(
    LocalDateTime.of(2026, 11, 1, 1, 30),
    ZoneId.of("America/New_York"),
    ZoneOffset.of("-05:00"));
// 2026-11-01T06:30:00Z
```

To support normal inputs, the caller can pass `requestedOffset = null`; the resolver automatically uses the single offset. For overlap times, the caller is forced to choose. This is an **explicit policy**, though a system may also choose "earlier occurrence" or "later occurrence" depending on product requirements. None of these policies should be assumed to be universally right for every business domain.

**Advanced note:** for real-world time zones, gap/overlap structures typically have 0/1/2 offsets; the resolver uses the `else` branch when there is more than one offset, though standard IANA data yields two for an overlap. For inputs missing a zone, the method above intentionally does not accept `null` as the zone.

## 11. Testing Java with Fixed Time

### 11.1. Test Cases to Include

| Case | LocalDateTime and zone/offset | Expected |
| --- | --- | --- |
| Fixed zone on example date | `2026-07-01T09:30` in `Asia/Ho_Chi_Minh` | `2026-07-01T02:30:00Z` |
| Valid offset | `2026-07-01T09:30+07:00` | Same `Instant` as above |
| Semantically wrong offset | `2026-07-01T09:30+09:00` but context is HCM | Mathematically valid `Instant` but **wrong business data** |
| DST gap | `2026-03-08T02:30` in `America/New_York` | Strict resolver rejects |
| DST overlap unchosen | `2026-11-01T01:30` in New York, offset `null` | Resolver rejects requiring a choice |
| DST overlap first occurrence | same local, offset `-04:00` | `2026-11-01T05:30:00Z` |
| DST overlap second occurrence | same local, offset `-05:00` | `2026-11-01T06:30:00Z` |
| Offset not belonging to zone | `2026-07-01T09:30` in New York, offset `-05:00` | `ofStrict`/resolver rejects |
| Zone conversion keeping instant | one `Instant`, HCM → New York | `toInstant()` before/after are equal |
| Difference across overlap | two 01:30 occurrences in New York | `Duration` between the two instants = 60 minutes |

To write assertions, you can use JUnit 5 in the project; there is no need to depend on the machine clock when the inputs are `LocalDateTime` and a fixed zone. If there is a "disallow booking in the past" feature, **inject `Clock`** into the service instead of calling `Instant.now()` inside each branch:

```java
import java.time.*;

Clock fixed = Clock.fixed(
    Instant.parse("2026-07-01T00:00:00Z"),
    ZoneOffset.UTC);
Instant now = Instant.now(fixed);
boolean inFuture = Instant.parse("2026-07-01T02:30:00Z").isAfter(now);
```

This is a snippet inside a method; `inFuture` is always `true`. Do not compare `LocalDateTime.now()` directly with the user's time when they belong to different zones. For future/past checks, compare **two resolved Instants**.

### 11.2. DST Tests Should Have a Specific Policy

A test that only checks `local.atZone(zone).toInstant()` may accidentally accept default adjustments at a gap/overlap that the product does not want. Test directly:

- Does it detect a gap and return an error message?
- Does it require choosing an offset at an overlap?
- If the caller selects an invalid offset, does it reject rather than compute arbitrarily?
- After resolving the offset, does converting between HCM/New York preserve the `Instant`?
- Are leap year dates, year boundaries, instants near midnight, and zones with non-whole-hour offsets like `Asia/Kathmandu` (currently `+05:45`) tested?

Future DST rules may change when tzdb is updated; if tests rely on future legal time policies, anchor expectations to the data version or use fixed historical instants with known outcomes.

## 12. Common Mistakes

1. **Implicitly assigning UTC to LocalDateTime.** `LocalDateTime.of(2026,7,1,9,30)` has no UTC; only call `toInstant(ZoneOffset.UTC)` if the source truly defines UTC.
2. **Using the server's default timezone to interpret user data.** On a server set to UTC, a 09:30 meeting in Ho Chi Minh City will be off by 7 hours if the business zone is not passed.
3. **Confusing ZoneId and ZoneOffset.** `-05:00` is a fixed offset; `America/New_York` is a region with DST and historical rules.
4. **Using `atOffset` with an offset not validated against the region.** The API can compute an instant, but it may be the wrong instant for the requirement; validate via `ZoneRules`/`ofStrict`.
5. **Assuming `atZone` always preserves the input LocalDateTime.** A gap can shift the time automatically, and an overlap can pick one of two offsets.
6. **Assuming local + zone always yields a single instant.** A DST overlap produces two instants and requires a choice or explicit policy.
7. **Converting time zones with `withZoneSameLocal` when you want to keep the same event.** Use `withZoneSameInstant` to preserve the UTC instant.
8. **Storing event timestamps as zoneless LocalDateTime.** Later you may not be able to recover the exact instant, especially if the server's timezone changes.
9. **Subtracting clock hours to measure elapsed time across DST.** Use `Instant` and `Duration`; a calendar day and a 24-hour span are two different concepts.
10. **Parsing a string with an offset into LocalDateTime and dropping the offset.** Use `OffsetDateTime.parse` or `ZonedDateTime.parse` with the proper type to preserve critical information.
11. **Storing only one offset for a long-term recurring schedule.** A region may switch DST; a weekly 09:00 schedule needs a ZoneId/recurrence rule.
12. **Forgetting that these types are immutable.** `zoned.withZoneSameInstant(otherZone)` does not mutate the original variable; you must keep the return value.
13. **Comparing time zones by formatted display text.** To know whether two appointments share the same instant, compare `toInstant()`, not local strings or hours/minutes alone.
14. **Believing time zone data is forever fixed.** Tzdb is updated as local laws change; do not apply a "current" offset to all years.
15. **Reusing the offset from right now for a future appointment.** A region's offset may differ on the scheduled date; query `zone.getRules()`/`atZone` for the exact target date-time.

## 13. Exercises from Basic to Practical

### Exercise 1 — Two Combination Paths Yielding the Same Instant

Given `LocalDateTime.of(2026,7,1,9,30)`. Create a `ZonedDateTime` using `Asia/Ho_Chi_Minh` and an `OffsetDateTime` using `+07:00`. Convert both to `Instant` and verify `equals` is `true`. Expected result: `2026-07-01T02:30:00Z`.

### Exercise 2 — Choosing the Wrong Offset

Keep the `LocalDateTime` from Exercise 1 but use `ZoneOffset.ofHours(9)`. Compute the new instant and explain why `2026-07-01T00:30:00Z` is mathematically valid for the offset calculation but **does not represent 09:30 in Ho Chi Minh City**.

### Exercise 3 — Converting Meeting Time to New York

Given the Ho Chi Minh City meeting at `2026-07-01T09:30+07:00`, display the time in New York using `withZoneSameInstant(ZoneId.of("America/New_York"))`. Result: `2026-06-30T22:30-04:00[America/New_York]`. Compare `toInstant` before/after and explain why the local date shifts to 06/30.

### Exercise 4 — Gap and Overlap

Given New York and two inputs `2026-03-08T02:30`, `2026-11-01T01:30`:

- Read `getValidOffsets(local)` for each value.
- Return an error when the list is empty.
- When the list has 2 elements, require a selection and use `ofStrict`.
- Print the two instants of `01:30` in the overlap: `05:30Z` and `06:30Z`.

### Exercise 5 — Developing a Scheduling API

Write an endpoint that accepts `localStart`, `timeZone`, and `selectedOffset` (which may be null if the offset is unique). Use the resolver from this lesson; if successful, return JSON containing `startInstant` and `organizerZone`. Test normal input, gap, overlap, wrong offset, and invalid zone.

### Exercise 6 — System Clock and CI

A service rejects bookings in the past based on `Instant.now(clock)`. Test using `Clock.fixed(Instant.parse("2026-07-01T00:00:00Z"), ZoneOffset.UTC)` to verify that an appointment at `02:30Z` is in the future. The test must be stable whether run on a machine in UTC or Asia/Ho_Chi_Minh.

### Exercise 7 — When Must Zone ID Be Stored?

An application stores the schedule "09:00 every Monday in New York for the next 12 months". Try modeling it by storing only the first `Instant` + 7 days × 24 hours, then explain why this does not guarantee 09:00 local time around DST. Propose storing the Monday 09:00 rule + `America/New_York` and constructing each occurrence.

## 14. Self-Assessment Checklist

- [ ] Can explain that `LocalDateTime` **does not carry a zone/offset** and why it is not yet enough to yield a UTC instant.
- [ ] Can create an `OffsetDateTime` with `atOffset` and an `Instant` with `toInstant(ZoneOffset)`.
- [ ] Can create a `ZonedDateTime` with `atZone(ZoneId)` and convert to `Instant`.
- [ ] Can choose the right region `ZoneId` when business logic requires local time rules; do not default to the server's offset.
- [ ] Can distinguish `ZoneOffset` (specific offset) and `ZoneId` (region with tzdb).
- [ ] Can detect gap/overlap via `ZoneRules.getValidOffsets`, and understand the default policy of `atZone`.
- [ ] Can use `ZonedDateTime.ofStrict` when validating a chosen offset is needed.
- [ ] Can use `withZoneSameInstant` to display the same instant in another zone; distinguish from `withZoneSameLocal`.
- [ ] Can design storage using `Instant` for confirmed events, along with `ZoneId` when the source zone must be retained.
- [ ] Can test with specific instants/dates/zones and `Clock.fixed` for logic depending on "now".
- [ ] Can build a resolver that handles gap/overlap explicitly before creating an official appointment.

## Official JDK 17 Documentation

- [LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [ZoneOffset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html)
- [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html)
- [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
