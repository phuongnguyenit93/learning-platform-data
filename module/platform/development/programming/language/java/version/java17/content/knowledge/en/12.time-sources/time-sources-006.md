# Distinguishing Instant, LocalDateTime, and ZonedDateTime in Java 17

Java 17 provides a modern date and time API in the `java.time` package. Three commonly encountered types are **`Instant`**, **`LocalDateTime`**, and **`ZonedDateTime`**, and they represent three different concepts:

- `Instant` is a **point on the timeline**, independent of display time zones.
- `LocalDateTime` is a **date and time on a local clock**, without a time zone or offset, so it does not yet identify a unique point in time.
- `ZonedDateTime` is a **local date and time tied to a time zone with rules**, in which a specific offset is resolved for that date and time.

Choosing the wrong type can shift appointment times, make log data hard to correlate, or cause timestamps to be misinterpreted when users are in different time zones. This lesson explains how to choose, create, convert, parse, handle daylight saving time (DST), and test these three types using official Java 17 APIs.

## 1. Three Concepts to Distinguish

Consider an event occurring at a real point in time. Someone in Vietnam might see the event at 15:00, while someone in Paris sees the same event at 09:00 or 10:00 depending on the date and DST rules. Two different displays can still point to **one single instant**.

| Type | Representation | Enough info to identify an instant? | Appropriate use cases |
| --- | --- | --- | --- |
| `Instant` | Time on the UTC timeline | Yes | When an event occurred, log timestamps, record creation time |
| `LocalDateTime` | Year-month-day and hour-minute-second-nano | No | Opening hours, unzoned appointment times, form date-time values |
| `ZonedDateTime` | Local date-time + zone ID + valid offset | Yes | Displaying an instant in a region, time-zone-aware appointments |

An example:

~~~java
Instant instant = Instant.parse("2026-11-15T08:00:00Z");

ZonedDateTime vietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime paris =
        instant.atZone(ZoneId.of("Europe/Paris"));

System.out.println(vietnam);
System.out.println(paris);
~~~

Both `ZonedDateTime` values represent the same `Instant`. The local date-time portions differ because the time zones have different offsets at that point in time.

## 2. Instant: A Point on the Timeline

`Instant` represents a point on the timeline, measured in seconds and nanoseconds from the epoch 1970-01-01T00:00:00Z. The `Z` symbol denotes UTC (zero offset).

~~~java
import java.time.Instant;

public class InstantDemo {
    public static void main(String[] args) {
        Instant now = Instant.now();
        Instant event = Instant.parse("2026-11-15T08:30:00Z");

        System.out.println("now   = " + now);
        System.out.println("event = " + event);
    }
}
~~~

`Instant.now()` retrieves the current instant from the system clock. `Instant.parse(...)` reads an ISO-8601 representation with a UTC offset in this example.

### 2.1. Instant Does Not Store a Local Time Zone

An `Instant` does not store a region name such as `Asia/Ho_Chi_Minh` or `Europe/Paris`. It identifies an absolute point in time; when displaying it, you must choose a zone:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-15T08:30:00Z");

ZonedDateTime local = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(local);
~~~

The zone is used to interpret or display the instant, without changing the underlying instant.

### 2.2. Operations on Instant

`Instant` supports linear time addition and subtraction:

~~~java
Instant start = Instant.parse("2026-11-15T08:00:00Z");

Instant end = start.plusSeconds(90);
Duration elapsed = Duration.between(start, end);

System.out.println(end);
System.out.println(elapsed.toSeconds()); // 90
~~~

Units such as seconds, milliseconds, microseconds, and nanoseconds fit the timeline. `Instant` does not natively know "tomorrow at 9 AM in Hanoi"; that is a local calendar rule and requires a zone.

### 2.3. Using Instant for Events That Have Occurred

Use `Instant` for:

- When an order was created or paid.
- When a request arrived at the server.
- Log or audit event timestamps.
- When a job actually started or finished.
- Timestamps exchanged between services.

When displaying, convert the instant to the viewer's zone. When storing, an instant keeps its exact meaning regardless of which time zone the server or user is in.

## 3. LocalDateTime: Local Date and Time Without a Zone

`LocalDateTime` consists of calendar and clock fields, such as `2026-11-15T15:30`. It **contains no offset and no zone ID**.

~~~java
import java.time.LocalDateTime;

public class LocalDateTimeDemo {
    public static void main(String[] args) {
        LocalDateTime meeting =
                LocalDateTime.of(2026, 11, 15, 15, 30);

        System.out.println(meeting);
    }
}
~~~

This value only says "November 15, 2026, at 15:30." Without knowing the time zone, it is impossible to conclude which instant on the timeline it represents.

The same `LocalDateTime` can correspond to different instants in Hanoi, Tokyo, or Paris. In some regions during DST transitions, a local date-time may not even exist or may occur twice.

### 3.1. When to Use LocalDateTime?

Appropriate when data is defined on a local clock and the zone is supplied separately, for example:

- A user enters an appointment time while the form stores the zone in a separate field.
- Shift start and end times defined by a location's schedule.
- Opening hours: 08:00–17:00, repeating by day of week.
- Date and time on an invoice or document representing local time at a location already established by context.

Do not use `LocalDateTime` alone as a system-wide timestamp if you need to know accurately whether one event happened before or after another.

### 3.2. LocalDateTime Is Not UTC

The word "local" does not mean the current machine's time, nor does it mean UTC. It simply means date and time components without zone information.

~~~java
LocalDateTime local = LocalDateTime.now();
~~~

The call above reads the date-time fields using the system's default time zone at the moment of the call. However, once created, the `LocalDateTime` value does not retain that time zone. If you want to specify the zone up front, pass `ZoneId` explicitly:

~~~java
LocalDateTime vietnamNow =
        LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

The result is still a `LocalDateTime`; `Asia/Ho_Chi_Minh` is only used to read the clock at the time of the call and is not stored in the object.

### 3.3. LocalDateTime Cannot Convert Itself to Instant

The following snippet has no valid API because it lacks a zone/offset:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 11, 15, 15, 30);

// There is no parameterless local.toInstant():
// a local date-time lacks enough information to identify an instant.
~~~

You must supply a `ZoneId` or `ZoneOffset` to resolve a local date-time into an instant.

## 4. ZonedDateTime: Date and Time Tied to a Time Zone

`ZonedDateTime` combines:

1. `LocalDateTime` – date and time components on a local clock.
2. `ZoneId` – region name and set of time-zone rules.
3. `ZoneOffset` – specific offset applied at that point in time.

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedDateTimeDemo {
    public static void main(String[] args) {
        ZonedDateTime meeting = ZonedDateTime.of(
                2026, 11, 15, 15, 30, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(meeting);
        System.out.println(meeting.getZone());
        System.out.println(meeting.getOffset());
    }
}
~~~

Output takes the form:

~~~text
2026-11-15T15:30+07:00[Asia/Ho_Chi_Minh]
Asia/Ho_Chi_Minh
+07:00
~~~

`Asia/Ho_Chi_Minh` is the zone ID; `+07:00` is the offset applied for that local date-time.

### 4.1. ZoneId and ZoneOffset Are Not the Same

- `ZoneOffset` is a fixed offset from UTC, such as `+07:00` or `-05:00`.
- `ZoneId` is typically a region ID such as `Asia/Ho_Chi_Minh` or `Europe/Paris`, tied to historical and future rules provided by the time-zone database (tzdb).
- A region zone may use different offsets on different dates due to historical legal changes or DST.

`ZoneOffset.UTC` is a valid fixed zone. However, using `ZoneOffset.ofHours(7)` instead of `ZoneId.of("Asia/Ho_Chi_Minh")` loses the region name and its rules. Only use a fixed offset when the data contract genuinely requires a fixed offset.

### 4.2. Converting ZonedDateTime to Instant

~~~java
ZonedDateTime zoned = ZonedDateTime.of(
        2026, 11, 15, 15, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant instant = zoned.toInstant();
~~~

Converting to `Instant` preserves the point on the timeline. You can then display the same instant in another zone:

~~~java
ZonedDateTime tokyo = instant.atZone(ZoneId.of("Asia/Tokyo"));
~~~

### 4.3. ZonedDateTime Can Produce an Instant

Unlike `LocalDateTime`, `ZonedDateTime` already has enough information to identify a point in time. Its `toInstant()` method converts it to an `Instant` without parameters.

## 5. Quick Selection Table

| Problem question | Typically suitable type | Reason |
| --- | --- | --- |
| When did the event actually happen? | `Instant` | Identifies a unique point in time |
| A user booked 09:00 at the Paris branch? | `LocalDateTime` + `ZoneId` or `ZonedDateTime` | Need to preserve local clock time and region |
| Displaying a timestamp to a user in Vietnam? | `Instant` converted to `ZonedDateTime` | Keep the instant, change the view |
| Repeating shift from 08:00 to 17:00 daily at a location? | `LocalTime` and location's zone | This is a local time rule, not a single instant |
| Birth date regardless of hour/time zone? | `LocalDate` | Calendar date only |
| A point in time with a fixed offset and no region rules needed? | `OffsetDateTime` or `Instant` per contract | Offset and zone ID have different meanings |

Do not pick a type just because it has more fields. Choose according to the semantics of the data the system must preserve.

## 6. Converting Between the Three Types

### 6.1. Instant to ZonedDateTime

This is the common conversion when displaying timestamps:

~~~java
Instant instant = Instant.parse("2026-11-15T08:00:00Z");

ZonedDateTime hanoi =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime tokyo =
        instant.atZone(ZoneId.of("Asia/Tokyo"));

System.out.println(hanoi);
System.out.println(tokyo);
System.out.println(hanoi.toInstant().equals(tokyo.toInstant())); // true
~~~

Both objects have different local times and zones, yet represent the same instant.

### 6.2. LocalDateTime to ZonedDateTime

When a user enters a local date and time and the application knows the zone:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 11, 15, 15, 0);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
~~~

`atZone(zone)` applies the zone's rules to find a valid offset. For normal dates and times, there is usually exactly one valid offset. During DST transitions, however, there may be zero or two valid offsets; the next section explains this in detail.

### 6.3. LocalDateTime to Instant via ZoneOffset

If the contract already specifies a fixed offset:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 11, 15, 15, 0);

Instant instant = local.toInstant(ZoneOffset.ofHours(7));
~~~

This resolves the instant using the offset. It does not look up region rules like `Asia/Ho_Chi_Minh`. If the data represents local time in a region with DST rules, use `ZoneId` instead of guessing an offset.

### 6.4. Instant Cannot Yield LocalDateTime Without Choosing a Zone

~~~java
Instant instant = Instant.now();

LocalDateTime utcFields =
        LocalDateTime.ofInstant(instant, ZoneOffset.UTC);

LocalDateTime hanoiFields =
        LocalDateTime.ofInstant(
                instant,
                ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

The two `LocalDateTime` values differ because different zones were chosen. The `Instant` itself remains unchanged.

## 7. Two Ways to Change Time Zones: Keep Instant or Keep Local Time

`ZonedDateTime` has two easily confused operations:

- `withZoneSameInstant(zone)`: **keeps the instant unchanged**, updates local time and offset to display in the new zone.
- `withZoneSameLocal(zone)`: attempts to **keep the local clock time unchanged**, swaps the zone and resolves the new offset; due to DST, the local time may be adjusted if invalid.

### 7.1. Keeping the Same Instant

~~~java
ZonedDateTime hanoi = ZonedDateTime.of(
        2026, 11, 15, 15, 0, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime paris = hanoi.withZoneSameInstant(
        ZoneId.of("Europe/Paris"));

System.out.println(hanoi.toInstant().equals(paris.toInstant())); // true
~~~

The time in Paris is calculated using Paris's offset at that instant. This is the right choice when displaying the same event to users in different time zones.

### 7.2. Keeping the Same Local Time

~~~java
ZonedDateTime hanoi = ZonedDateTime.of(
        2026, 11, 15, 15, 0, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime parisSameLocal = hanoi.withZoneSameLocal(
        ZoneId.of("Europe/Paris"));

System.out.println(hanoi.toLocalDateTime());
System.out.println(parisSameLocal.toLocalDateTime());
System.out.println(hanoi.toInstant().equals(parisSameLocal.toInstant()));
~~~

On normal dates and times, the two local date-times can match, yet the instants differ because the offsets differ. This means "keeping the same clock reading," not keeping the same event on the timeline.

### 7.3. Choosing the Right Operation

| Goal | Use |
| --- | --- |
| A meeting whose instant is fixed, displayed to a user in another zone | `withZoneSameInstant` |
| Moving a "still 09:00" rule to a different zone | `withZoneSameLocal`, after confirming business intent |
| Converting user-entered date-time into a point in time | `LocalDateTime.atZone(zone)` with DST handling |
| Changing string formatting only, without changing data | `DateTimeFormatter` |

## 8. DST: Why a LocalDateTime May Not Be Uniquely Defined

Some regions adjust clocks seasonally (Daylight Saving Time, DST). When switching to summer time, the clock jumps forward and skips a range of local times. When returning to standard time, the clock falls back and repeats a range of local times.

Thus, for a `LocalDateTime` in a zone, there are three cases:

1. **Normal:** exactly one valid offset.
2. **Gap:** no valid offset because the clock jumped over that hour.
3. **Overlap:** two valid offsets because the clock repeated that hour.

Not all zones observe DST; for instance, `Asia/Ho_Chi_Minh` currently uses offset +07:00 with no DST rules under current tzdb data. However, applications handling global schedules must account for each region's rules.

### 8.1. Checking with ZoneRules

`ZoneId` provides `ZoneRules` to query valid offsets at a `LocalDateTime`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

ZoneId paris = ZoneId.of("Europe/Paris");
ZoneRules rules = paris.getRules();

LocalDateTime local =
        LocalDateTime.of(2024, 3, 31, 2, 30);

System.out.println(rules.getValidOffsets(local));
System.out.println(rules.getTransition(local));
~~~

Under Paris's DST rules on the example date, `02:30` lies inside a gap, so the list of valid offsets is empty. `getTransition(local)` provides information about the transition causing the gap.

This is why `LocalDateTime` alone cannot accurately represent an event on the timeline.

### 8.2. Gap: Non-Existent Local Time

In Paris on 2024-03-31, clocks move from 02:00 to 03:00. Hence `2024-03-31T02:30` does not exist under that region's rules.

When calling:

~~~java
LocalDateTime local =
        LocalDateTime.of(2024, 3, 31, 2, 30);

ZonedDateTime resolved = local.atZone(ZoneId.of("Europe/Paris"));

System.out.println(resolved);
~~~

Java adjusts the local time forward by the length of the gap to produce a valid time. For this example, the output is:

~~~text
2024-03-31T03:30+02:00[Europe/Paris]
~~~

This is the default behavior of `atZone` when a local date-time falls in a gap. It is convenient for many cases, though not always the desired business rule. For instance, train scheduling or shift booking may require rejecting non-existent times instead of silently pushing them forward.

### 8.3. Overlap: Local Time Occurring Twice

In Paris on 2024-10-27, the hour from 02:00 to 02:59 occurs twice: once with summer offset +02:00 and once with standard offset +01:00.

~~~java
LocalDateTime local =
        LocalDateTime.of(2024, 10, 27, 2, 30);

ZoneId paris = ZoneId.of("Europe/Paris");

System.out.println(paris.getRules().getValidOffsets(local));
~~~

The output has two valid offsets:

~~~text
[+02:00, +01:00]
~~~

Two distinct instants both display as 02:30. `LocalDateTime` cannot distinguish these two occurrences.

`ZonedDateTime.of(...)` and `LocalDateTime.atZone(...)` default to choosing the earlier offset in an overlap (typically the summer offset, +02:00 in this example). If you need the other occurrence, use `withLaterOffsetAtOverlap()`:

~~~java
ZonedDateTime first = local.atZone(paris);
ZonedDateTime second = first.withLaterOffsetAtOverlap();

System.out.println(first);
System.out.println(second);
System.out.println(Duration.between(
        first.toInstant(), second.toInstant()).toMinutes());
~~~

Output:

~~~text
2024-10-27T02:30+02:00[Europe/Paris]
2024-10-27T02:30+01:00[Europe/Paris]
60
~~~

The two displayed clock times look identical, yet their instants are 60 minutes apart.

### 8.4. Rejecting Gap Times or Asking Users to Choose on Overlap

If the application needs strict control, query valid offsets first:

~~~java
List<ZoneOffset> offsets =
        paris.getRules().getValidOffsets(local);

if (offsets.isEmpty()) {
    throw new IllegalArgumentException(
            "Local time does not exist due to DST transition");
}

if (offsets.size() == 2) {
    // Business logic required to choose earlier or later offset.
}
~~~

For overlap cases, you can store the chosen offset alongside the appointment to pinpoint the exact instant. If you simply call `atZone` without recording a selection policy, the application implicitly accepts Java's default rule.

## 9. Parsing and Formatting the Three Types with ISO-8601

`java.time` provides built-in ISO formatters suitable for many interchange formats.

| Type | Formatter | Example |
| --- | --- | --- |
| `Instant` | `DateTimeFormatter.ISO_INSTANT` | `2026-11-15T08:30:00Z` |
| `LocalDateTime` | `DateTimeFormatter.ISO_LOCAL_DATE_TIME` | `2026-11-15T15:30:00` |
| `ZonedDateTime` | `DateTimeFormatter.ISO_ZONED_DATE_TIME` | `2026-11-15T15:30:00+07:00[Asia/Ho_Chi_Minh]` |

Parsing:

~~~java
Instant instant =
        Instant.parse("2026-11-15T08:30:00Z");

LocalDateTime local =
        LocalDateTime.parse("2026-11-15T15:30:00");

ZonedDateTime zoned =
        ZonedDateTime.parse(
                "2026-11-15T15:30:00+07:00[Asia/Ho_Chi_Minh]");
~~~

Explicit formatting:

~~~java
String instantText =
        DateTimeFormatter.ISO_INSTANT.format(instant);

String localText =
        DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local);

String zonedText =
        DateTimeFormatter.ISO_ZONED_DATE_TIME.format(zoned);
~~~

A string containing only `2026-11-15T15:30:00` lacks enough information to parse into an `Instant`. An `Instant` string requires a UTC/offset designator or must be combined with a zone/offset from another source.

### 9.1. ISO Strings and Stored Data

- Storing `Instant` in UTC ISO format makes exchanging timestamps between systems easy.
- Store `LocalDateTime` if the data contract intentionally carries only local date and time; store the zone separately when resolving the instant is needed.
- Store `ZonedDateTime` in ISO format with both offset and zone ID if you need to preserve both the instant and the original display region.

If an API requires a custom format, use `DateTimeFormatter` with an explicit pattern. Do not slice strings or add/subtract hours manually to convert time zones.

## 10. Clock: Controlling the Time Source and Writing Stable Tests

A method calling `Instant.now()` directly depends on the system clock. Tests running at different times receive different values, making time-based logic hard to test.

`Clock` allows passing a time source in:

~~~java
import java.time.Clock;
import java.time.Instant;

public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = clock;
    }

    public Instant createdAt() {
        return clock.instant();
    }
}
~~~

In production:

~~~java
AuditService service =
        new AuditService(Clock.systemUTC());
~~~

In tests, use a fixed clock:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-15T08:00:00Z"),
        ZoneOffset.UTC);

AuditService service = new AuditService(fixed);

System.out.println(service.createdAt());
// 2026-11-15T08:00:00Z
~~~

`Clock.fixed` keeps time constant in tests. This is useful for checking expiration, record creation timestamps, warranty periods, or deadline logic.

If code needs local time in a zone, use `clock.withZone(zone)` or obtain `ZonedDateTime.now(clock)`. Avoid letting multiple classes call `LocalDateTime.now()` with different default zones, as results will depend on the runtime environment.

## 11. Duration and Period: Measuring Intervals with the Right Meaning

When computing the distance between points in time, `Duration` represents an amount of time in seconds/nanoseconds. When computing calendar distances, `Period` represents years/months/days.

~~~java
Instant start = Instant.parse("2026-11-15T08:00:00Z");
Instant end = start.plus(Duration.ofHours(2));

Duration elapsed = Duration.between(start, end);
~~~

With a local calendar:

~~~java
LocalDate today = LocalDate.of(2026, 11, 15);
LocalDate nextMonth = today.plus(Period.ofMonths(1));
~~~

A calendar day is not always equal to 24 hours on the timeline in regions with DST. If you need to add "one calendar day" to an appointment, operate on `ZonedDateTime`/`LocalDate` with the appropriate zone. If you need to add exactly 24 elapsed hours, operate on `Instant` using `Duration.ofHours(24)`.

Example:

~~~java
ZonedDateTime before = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime sameLocalTimeTomorrow = before.plusDays(1);
ZonedDateTime after24Hours = before.plus(Duration.ofHours(24));
~~~

Across a DST transition, the two results can differ in either local time or instant. You need to clarify whether the requirement means "same time tomorrow" or "exactly 24 hours later."

## 12. Choosing Data Types When Designing Systems

### 12.1. Logs and Audits

Store `Instant` for when an event actually occurred:

~~~java
record AuditEvent(String action, Instant occurredAt) {
}
~~~

When displaying, convert to the viewer's zone or the zone required by the report. Do not store log timestamps solely as `LocalDateTime`, because you lose the information needed to sort events accurately across machines in multiple time zones.

### 12.2. Future Appointments

An appointment such as "09:00 on April 10 at the Paris branch" represents local time in a region. You can store:

- `LocalDateTime`: the selected date and time.
- `ZoneId`: `Europe/Paris`.
- Gap/overlap handling policy if the time can fall on a DST transition.

If the appointment has been confirmed as a specific instant, you can also store the corresponding `Instant` for reminders, synchronization, and auditing. When time-zone rules are updated, the product must decide whether to prioritize preserving "09:00 local time" or preserving the locked-in instant.

### 12.3. Opening Hours and Recurring Schedules

Opening hours of 08:00–17:00 Monday through Friday are not a single instant. The appropriate model is typically `LocalTime`, day of week, and the location's `ZoneId`. Each concrete day is then combined with zone rules to produce actual instants.

### 12.4. Birthdays or Anniversaries

If only the calendar date matters, use `LocalDate`. Do not turn a birthday into an `Instant` at 00:00 UTC and display it in another zone, or users may see the previous or next day.

## 13. Common Mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Same timestamp displays different hours in UI | Converting the same instant to different zones | This is expected behavior; standardize display zone |
| Don't know which instant a LocalDateTime corresponds to | Missing zone or offset | Combine with `ZoneId` or `ZoneOffset` |
| Appointment shifts when user travels | Storing local date-time and implicitly using server default zone | Store zone ID for the appointment's location |
| Local time does not exist when DST starts | Local time falls in a gap | Reject, adjust, or prompt per business policy |
| Local time appears twice when DST ends | Local time falls in an overlap | Explicitly select earlier/later offset |
| Using fixed offset for a region with DST | Confusing ZoneOffset with ZoneId | Use region ID and zone rules |
| Adding 24 hours changes the local clock hour | Using Duration when calendar day was intended | Distinguish Duration from Period/plusDays |
| Time tests change depending on the run day | Calling now directly | Inject Clock and use Clock.fixed in tests |
| Birthday shifts by one day | Using Instant for date-only data | Use LocalDate |
| Logs cannot be sorted across time zones | Storing only LocalDateTime | Store Instant, convert zone at display time |
| Manually adding/subtracting hours to change time zones | Ignoring zone rules and DST | Use atZone/withZoneSameInstant |

## 14. Comprehensive Runnable Example on Java 17

Create `TimeTypesDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class TimeTypesDemo {

    private TimeTypesDemo() {
    }

    public static void main(String[] args) {
        Instant event = Instant.parse("2026-11-15T08:00:00Z");

        ZoneId hanoiZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId parisZone = ZoneId.of("Europe/Paris");

        ZonedDateTime hanoi = event.atZone(hanoiZone);
        ZonedDateTime paris = event.atZone(parisZone);

        System.out.println("Instant: " + event);
        System.out.println("Hanoi:   " + hanoi);
        System.out.println("Paris:   " + paris);
        System.out.println("Same instant: "
                + hanoi.toInstant().equals(paris.toInstant()));

        LocalDateTime appointment =
                LocalDateTime.of(2026, 11, 16, 9, 0);

        ZonedDateTime appointmentInHanoi =
                appointment.atZone(hanoiZone);

        System.out.println("Local appointment: " + appointment);
        System.out.println("Resolved appointment: "
                + appointmentInHanoi);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 TimeTypesDemo.java
java TimeTypesDemo
~~~

Output takes the form:

~~~text
Instant: 2026-11-15T08:00:00Z
Hanoi:   2026-11-15T15:00+07:00[Asia/Ho_Chi_Minh]
Paris:   2026-11-15T09:00+01:00[Europe/Paris]
Same instant: true
Local appointment: 2026-11-16T09:00
Resolved appointment: 2026-11-16T09:00+07:00[Asia/Ho_Chi_Minh]
~~~

Paris's time depends on the zone rules for the chosen date. The goal of the example is to show that the same `Instant` has multiple displays and that `LocalDateTime` requires a zone to resolve into a `ZonedDateTime`.

## 15. Practice Exercises

### Exercise 1 — Same Instant in Two Regions

Create a fixed `Instant`. Convert it to `Asia/Ho_Chi_Minh` and `Europe/Paris`. Print local date-time, offset, and zone; verify both results share the same `toInstant()`.

### Exercise 2 — LocalDateTime Missing Information

Create a `LocalDateTime` for a meeting at 09:00. Explain why it cannot yet be converted into an `Instant` without knowing the zone. Try converting it under two different zones and compare results.

### Exercise 3 — Keep Instant or Keep Local Time?

Create a `ZonedDateTime` in Hanoi. Call `withZoneSameInstant` and `withZoneSameLocal` to convert to Paris. Print the results and explain which method preserves the instant.

### Exercise 4 — DST Gap

Use `Europe/Paris` with `2024-03-31T02:30`. Inspect `getValidOffsets`, `getTransition`, and the result of `atZone`. Describe Java's default policy when a local time does not exist.

### Exercise 5 — DST Overlap

Use `Europe/Paris` with `2024-10-27T02:30`. Print the two valid offsets. Create two `ZonedDateTime` instances for the earlier and later offsets, then calculate the difference between their instants.

### Exercise 6 — Testing with Clock

Write a service returning record creation timestamps using `Clock`. Use `Clock.fixed` to test that the result stays constant across calls.

### Exercise 7 — Adding Calendar Days vs. Adding 24 Hours

Choose the day before a DST transition in Paris. Compare `plusDays(1)` and `plus(Duration.ofHours(24))`. Explain the two different business requirements.

## 16. Principles to Remember

- **`Instant`:** use when identifying an actual point on the timeline, independent of display time zones.
- **`LocalDateTime`:** use when storing date and time on a local clock whose zone is managed separately or not yet chosen; not enough to identify an instant.
- **`ZonedDateTime`:** use when needing local date-time together with zone rules and the offset applicable at that point in time.
- **`ZoneId`** describes a region and its rules; **`ZoneOffset`** is only a fixed offset from UTC.
- When changing zones, distinguish preserving the instant from preserving the local date-time.
- DST can create a gap (no valid offset) or overlap (two valid offsets); establish an explicit policy for appointments.
- Use `Clock` to control the time source and write reproducible tests.
- Distinguish linear duration `Duration` from calendar interval `Period`.

When choosing the right data type for the business semantics, a Java 17 application can store timestamps, process appointments, and display times across time zones cleanly, avoiding manual hour math and avoiding loss of information during conversions.
