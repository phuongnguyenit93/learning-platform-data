# Choosing Date-Only, Local Time, or Instant Data for Storage

## 1. The storage type must preserve the data's meaning

A field named `date` can represent a birth date, an opening hour, an appointment in a city, or the instant an event occurred. Those pieces of data do not share the same contract even though they are all represented using date-time digits.

Before choosing a database column or a JSON format, answer this question: **what does the data describe, and does it need to identify a single point on the timeline?**

| Meaning | Initial suitable Java type | Information preserved |
|---|---|---|
| Birth date, accounting date, selected date without time | `LocalDate` | Year-month-day |
| Daily opening hour | `LocalTime` | Hour-minute-second, without date/zone |
| Date-time seen on a clock in a locality | `LocalDateTime` | Date and time, without zone/offset |
| An event that occurred or a deadline at a specific point in time | `Instant` | A point on the timeline |
| Date-time with the UTC offset from the source data | `OffsetDateTime` | Date-time and offset |
| Date-time that needs to preserve a regional time zone | `ZonedDateTime`, or a model separating the required fields | Date-time, zone, and corresponding offset |

Type names help reveal meaning in code. The storage/exchange contract must still state that information explicitly; merely naming a column “timestamp” is not enough to prove the system preserves the right semantics.

## 2. Date-only data: do not invent hours and time zones that are not in the data

A birth date `2000-10-25` usually only needs `LocalDate`. It does not mean “an instant at midnight” and has no time zone to convert back and forth.

If you arbitrarily add Vietnam midnight and convert it to UTC, the UTC date becomes October 24. Another party that extracts only the date part from UTC could turn the birth date into the previous day.

This is not a time zone conversion bug. You turned a pure date into an instant by adding information the source data did not contain, and then discarded the time part elsewhere.

For storage, choose a date-without-time representation supported by your system; for exchange, a string like `2000-10-25` can be specified as an ISO date. Do not append a `Z` suffix to a date just to make every field look like a timestamp.

If the requirement is “valid through the end of October 25 in zone X”, the date and zone X together determine the instant boundary. That is an additional business decision, distinct from automatically treating every `LocalDate` as UTC midnight.

## 3. Local time: preserve clock intent without pretending you have an instant

### LocalTime for a time of day

`09:00` can be a regular opening hour. `LocalTime` holds the time part, but calculating a specific opening occurrence requires a date, a zone, and an operating schedule. Do not pick an arbitrary date such as 1970-01-01 to store a time and accidentally let that date participate in comparisons.

An operating schedule may require days of the week, holidays, closing hours, or shifts crossing midnight. Storing only `LocalTime` is one component, not a complete model of a recurring schedule.

### LocalDateTime for a date-time without a zone

The string `2026-10-25T09:00` describes a local date-time. It is not enough to say where in the world the event occurs at the same moment.

If you attach the Vietnam zone, the result is `2026-10-25T02:00:00Z`. If you interpret the same fields in UTC, the result is `2026-10-25T09:00:00Z`. The difference comes from the added context, not from `LocalDateTime` secretly holding a hidden zone.

If a system stores a `LocalDateTime` with the convention “these fields are in UTC”, that convention must be published and enforced consistently. The type itself does not prevent a caller from mistakenly interpreting it in the server's time zone. When the data is truly an instant, using an instant-representing type in the business layer helps avoid relying on implicit conventions.

## 4. Instants: store a single point in time, format by zone when needed

An event such as “when the request was received” can be stored as an `Instant`. A point in time like `2026-10-24T18:30:00Z` can be presented as:

```text
UTC:               2026-10-24 18:30
Vietnam:           2026-10-25 01:30
```

Storing the instant as the source of truth allows consistent before/after comparisons and duration calculations. Local dates used for reporting should be derived using the chosen reporting time zone.

If you need to know the user's original zone, a single `Instant` does not retain that information. You can additionally store the zone ID or source offset as required. Conversely, storing only `+07:00` does not fully describe the rules of a geographic region across past or future history.

Do not treat an offset and a `ZoneId` as the same kind of data:

- An offset is a specific displacement such as `+07:00`.
- A regional `ZoneId` such as `Asia/Ho_Chi_Minh` references a set of rules over time.

When the recipient only needs a global point in time, an `Instant`/UTC contract may be sufficient. When you need to reconstruct the source context or future zone-based appointments, preserve that exact additional information.

## 5. Future appointments need a policy when local time is not uniquely defined

Storing `LocalDateTime` alongside `ZoneId` expresses the intent “09:00 in this zone”. However, in zones with DST, there are local times that do not exist or occur twice.

`zone.getRules().getValidOffsets(localDateTime)` returns the valid offsets:

| Typical offset count | Situation | Decision needed |
|---|---|---|
| 0 | Skipped time interval (gap) | Reject or shift according to a published rule |
| 1 | Normal unambiguous date-time | Create the instant from that offset |
| 2 | Repeated time interval (overlap) | Pick the earlier/later occurrence or ask for clarification |

Do not simply call a zone-attachment operation with default adjustment behavior and assume the data always carries the meaning the user intended. The example program below chooses a simple policy: **accept only when there is exactly one offset**, and report an error if it is missing or ambiguous.

Zone rule data can be updated. For future appointments, you must decide what the source of truth is: keep the resolved `Instant` fixed, or keep the local date-time/zone intent and recompute when rules change. You can store both the intent and the resolved instant along with the necessary context, but you must have a policy for handling discrepancies; storing extra fields does not resolve conflicts on its own.

## 6. Storage and exchange contracts

An illustrative JSON representation where each field has a separately defined meaning:

```json
{
  "birthDate": "2000-10-25",
  "dailyOpeningTime": "09:00",
  "appointmentLocalDateTime": "2026-10-25T09:00",
  "appointmentZoneId": "Asia/Ho_Chi_Minh",
  "occurredAt": "2026-10-24T18:30:00Z"
}
```

This is only an example of data shape, not an auto-running serializer configuration. The contract needs to specify which fields are required, the relationship between appointment fields, and how values are validated.

For numeric epochs, you must publish the unit: seconds, milliseconds, or a seconds/fractional-part pair. A number does not carry unit information on its own; misunderstanding it can produce an instant off by a factor of a thousand in distance from the epoch.

For databases, choose column types based on semantics and the documentation of the DBMS/driver in use. Do not assume every type named “timestamp with time zone” preserves the regional `ZoneId`, the source offset, or performs the same conversions. If the zone is data that must be preserved, verify and store it explicitly when the column type does not retain it.

Verify with read/write tests through the real layer:

- Does a date-only value remain unchanged when the environment changes time zones?
- Does reading back an instant preserve the exact same point in time?
- Does the driver, database session, or ORM implicitly apply a default time zone?
- Is fractional precision preserved to seconds, milliseconds, microseconds, or nanoseconds?
- Are required `ZoneId`/offset values still intact after an exchange round-trip?

Do not use a pure Java example to claim that all JDBC, ORM, or database mappings have been verified.

## 7. Complete runnable program

Save the following code to `StorageMeaningDemo.java`. The program uses Java 17 or later and requires no external libraries. It demonstrates data meaning and zone resolution without opening a database connection.

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StorageMeaningDemo {
    record AppointmentIntent(LocalDateTime localDateTime, ZoneId zone) {}

    static Instant resolveUnique(AppointmentIntent intent) {
        List<ZoneOffset> offsets = intent.zone().getRules()
                .getValidOffsets(intent.localDateTime());
        if (offsets.size() != 1) {
            throw new DateTimeException("local time is missing or ambiguous");
        }
        return ZonedDateTime.ofStrict(intent.localDateTime(),
                offsets.get(0), intent.zone()).toInstant();
    }

    public static void main(String[] args) {
        LocalDate birthday = LocalDate.parse("2000-10-25");
        LocalTime dailyOpening = LocalTime.parse("09:00");
        LocalDateTime appointment = LocalDateTime.parse("2026-10-25T09:00");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        System.out.println("dateOnly=" + birthday);
        System.out.println("timeOnly=" + dailyOpening);
        System.out.println("localDateTime=" + appointment);
        System.out.println("appointmentVietnam="
                + resolveUnique(new AppointmentIntent(appointment, vietnam)));
        System.out.println("appointmentUtc="
                + resolveUnique(new AppointmentIntent(
                        appointment, ZoneOffset.UTC)));

        Instant occurredAt = Instant.parse("2026-10-24T18:30:00Z");
        System.out.println("eventUtc="
                + occurredAt.atZone(ZoneOffset.UTC));
        System.out.println("eventVietnam=" + occurredAt.atZone(vietnam));
        System.out.println("eventRoundTrip="
                + occurredAt.equals(Instant.parse(occurredAt.toString())));

        Instant inventedMidnight = birthday.atStartOfDay(vietnam).toInstant();
        System.out.println("birthdayAfterUtcConversion="
                + inventedMidnight.atZone(ZoneOffset.UTC).toLocalDate());

        ZoneId newYork = ZoneId.of("America/New_York");
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        System.out.println("gapOffsetCount="
                + newYork.getRules().getValidOffsets(gap).size());
        System.out.println("overlapOffsetCount="
                + newYork.getRules().getValidOffsets(overlap).size());
        try {
            resolveUnique(new AppointmentIntent(overlap, newYork));
        } catch (DateTimeException e) {
            System.out.println("ambiguousAppointment=ERROR");
        }
    }
}
```

Compile and run:

```shell
javac StorageMeaningDemo.java
java StorageMeaningDemo
```

Verified output on Zulu OpenJDK 24.0.2 with that JDK's time zone data:

```text
dateOnly=2000-10-25
timeOnly=09:00
localDateTime=2026-10-25T09:00
appointmentVietnam=2026-10-25T02:00:00Z
appointmentUtc=2026-10-25T09:00:00Z
eventUtc=2026-10-24T18:30Z
eventVietnam=2026-10-25T01:30+07:00[Asia/Ho_Chi_Minh]
eventRoundTrip=true
birthdayAfterUtcConversion=2000-10-24
gapOffsetCount=0
overlapOffsetCount=2
ambiguousAppointment=ERROR
```

`ERROR` is the program's label when the `resolveUnique` policy rejects an ambiguous time. The DST examples rely on the zone rule set in the runtime environment; when changing JDKs or zone data, check the relevant transition cases.

The appointment lines show that the same local date-time can become two different `Instant` values if the zone differs. The two event lines show that the same `Instant` has two local views. These two directions must not be confused.

`birthdayAfterUtcConversion` intentionally demonstrates a design bug: assigning midnight to convert a birth date and then taking the UTC date causes the date value to change. Do not use that step in actual birth date storage.

## 8. Decisions to preserve in the data model

### Absence of a value is different from a default value

A missing time does not automatically mean `00:00`. A missing zone does not automatically mean UTC or the server's zone. If the data allows missing components, model the missing state and decide how to fill it in where the context exists.

### Precision is part of the contract

A Java type supporting nanoseconds does not guarantee the storage path preserves nanoseconds. If a column only stores milliseconds, you must choose a truncation/rounding strategy and check its impact on comparisons, expiration times, unique keys, or event ordering. Two events at different instants can become the same timestamp after precision reduction.

### Display language does not dictate source data format

Strings like `25/10/2026`, Vietnamese month names, or long formatted labels are for human readers. Internal values and exchange contracts need a clearly published syntax. Do not store a raw UI label and expect every environment to parse it back with the same locale.

### Local dates for reporting require a reporting zone

If you store events as `Instant` but want to group them by business day in a locality, convert using the reporting zone before extracting `LocalDate`. Taking the UTC date and changing the label to Vietnamese does not turn that group into a Vietnam-day group.

## 9. Practice on your own

Choose the representation for each case:

| Case | Meaningful choice |
|---|---|
| Issue date on an official document without time | `LocalDate` |
| Daily opening hour of a branch | `LocalTime`, paired with a zone and operating schedule in the calendar model |
| Instant the server received an event | `Instant`, optionally with source context if needed |
| Appointment at 09:00 in New York | Local date-time + `ZoneId` + gap/overlap policy and resolved instant |
| Source time sent with an offset that must be preserved | `OffsetDateTime` or exchange fields that preserve both the instant and the offset |

Then try changing the appointment's zone in the program while keeping `LocalDateTime` unchanged, and changing the event's display zone while keeping `Instant` unchanged. Explain why the first operation changes the point in time, whereas the second only changes the view of the same point in time.

Reference: [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html), [LocalTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html), and [ZoneRules — getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime)) in Java SE 21.
